"""LLM layer: one small protocol, an Anthropic client, a no-LLM template client, and a replay cache.

Another provider = another class with the same two methods (complete_json, complete_text).

The LLM is only used for (1) query planning and (2) answer wording. Its output is always validated by code.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

MAX_TOKENS = 1024
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"   # repo root, independent of the working directory


class CacheMiss(KeyError):
    pass


class LLMClient(Protocol):
    name: str
    model: str | None

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel: ...
    def complete_text(self, system: str, messages: list[dict]) -> str: ...


def strict_schema(schema: type[BaseModel]) -> dict:
    """JSON schema with additionalProperties=false and every property required, on every object."""
    js = copy.deepcopy(schema.model_json_schema())

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(js)
    return js


class TemplateClient:
    """No-LLM provider. The planner uses rule_plan and generation uses the extractive renderer instead."""

    name = "template"
    model = None

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        raise NotImplementedError("template provider: planning uses rule_plan()")

    def complete_text(self, system: str, messages: list[dict]) -> str:
        raise NotImplementedError("template provider: answers use render_template()")


class AnthropicClient:
    name = "anthropic"

    def __init__(self, model: str) -> None:
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:  # lazy, so replay mode works without a key
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        import anthropic

        js = strict_schema(schema)
        messages = [{"role": "user", "content": user}]
        try:  # structured outputs (anthropic SDK: output_config.format)
            resp = self.client.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system, messages=messages,
                output_config={"format": {"type": "json_schema", "schema": js}},
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            return schema.model_validate_json(text)
        except anthropic.BadRequestError:
            # fallback: one forced tool call whose input_schema is the plan schema
            resp = self.client.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=system, messages=messages,
                tools=[{"name": "emit_plan", "description": "Return the plan.", "input_schema": js}],
                tool_choice={"type": "tool", "name": "emit_plan"},
            )
            block = next(b for b in resp.content if b.type == "tool_use")
            return schema.model_validate(block.input)

    def complete_text(self, system: str, messages: list[dict]) -> str:
        # this SDK version takes no temperature parameter; determinism comes from the replay cache
        resp = self.client.messages.create(model=self.model, max_tokens=MAX_TOKENS, system=system, messages=messages)
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class ReplayCache:
    """Wrap any client. record: serve from cache, else call and store; replay: cache only (CacheMiss otherwise)."""

    def __init__(self, inner: LLMClient, mode: str, dir: str | Path = CACHE_DIR) -> None:
        self.inner, self.mode, self.dir = inner, mode, Path(dir)
        self.name = inner.name
        self.model = getattr(inner, "model", None)

    def _key(self, method: str, system: str, payload, schema: type[BaseModel] | None) -> str:
        blob = json.dumps(
            [self.name, self.model, method, system, payload, schema.model_json_schema() if schema else None],
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def _load(self, key: str):
        path = self.dir / f"{key}.json"
        if not path.is_file():
            raise CacheMiss(key)
        return json.loads(path.read_text())["output"]

    def _store(self, key: str, method: str, output) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{key}.json").write_text(json.dumps({"method": method, "provider": self.name, "model": self.model,
                                                         "output": output}, indent=1, ensure_ascii=False))

    def _cached(self, key: str, method: str, call):
        """replay: cache only. record: cache first, else call the provider once and store (first answer sticks,
        so a re-run replays the same conversation even though the model is not deterministic)."""
        if self.mode in ("replay", "record"):
            try:
                return self._load(key)
            except CacheMiss:
                if self.mode == "replay":
                    raise
        output = call()
        if self.mode == "record":
            self._store(key, method, output)
        return output

    def complete_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        key = self._key("complete_json", system, user, schema)
        out = self._cached(key, "complete_json", lambda: self.inner.complete_json(system, user, schema).model_dump(mode="json"))
        return schema.model_validate(out)

    def complete_text(self, system: str, messages: list[dict]) -> str:
        key = self._key("complete_text", system, messages, None)
        return self._cached(key, "complete_text", lambda: self.inner.complete_text(system, messages))


def make_client(settings) -> LLMClient:
    if settings.provider == "template":
        return TemplateClient()
    if settings.provider != "anthropic":
        raise ValueError(f"unknown provider {settings.provider!r}")
    inner = AnthropicClient(settings.model)
    return inner if settings.replay_mode == "off" else ReplayCache(inner, settings.replay_mode)
