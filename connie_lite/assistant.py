"""One conversational turn: plan -> retrieve -> gate -> generate (-> validate) -> state + trace.

Shared by the CLI, the demo script and the eval harness.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .answer.generate import Answer, generate
from .answer.llm import make_client
from .config import Settings, clamp_hops, load_settings
from .graph.build import build_graph
from .graph.ingest import PACKAGE_ROOT, build_alias_table, load_corpus
from .retrieval.evidence import attach_context, retrieve
from .retrieval.gate import gate
from .retrieval.planner import plan
from .retrieval.text_index import AlertIndex
from .schema import Alert
from .state import ConversationState


def path_to_dict(p) -> dict:
    return {"score": p.score, "edges": [{"src": e.src, "rel": e.rel, "dst": e.dst, "status": e.status,
                                         "supports": [s.label() for s in e.supports]} for e in p.edges]}


def write_trace(trace: dict, directory: str | Path) -> None:
    """One JSON file per turn: question, plan, kept paths with supports, gate, prompts, raw LLM output, answer."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    (Path(directory) / f"{trace['trace_id']}.json").write_text(json.dumps(trace, indent=1, default=str, ensure_ascii=False))


class Assistant:
    def __init__(self, settings: Settings | None = None, llm=None, profile: dict | None = None,
                 alerts: list[Alert] | None = None, trace_dir: str | Path | None = "traces") -> None:
        self.settings = settings or load_settings()
        if profile is None or alerts is None:
            data_dir = self.settings.data_dir
            profile, alerts = load_corpus(data_dir if data_dir.is_dir() else PACKAGE_ROOT / data_dir)
        self.profile = profile
        self.alerts = {a.id: a for a in alerts}
        self.aliases = build_alias_table(profile)
        self.store = build_graph(profile, alerts)
        self.index = AlertIndex(alerts)
        self.llm = llm if llm is not None else make_client(self.settings)
        self.state = ConversationState()
        self.max_hops = self.settings.max_hops
        self.trace_dir = trace_dir
        self.turn = 0
        self.last_trace: dict = {}
        self.last_answer: Answer | None = None
        self.last_evidence = None
        self.last_plan = None

    def set_hops(self, n: int) -> int:
        self.max_hops = clamp_hops(n)
        return self.max_hops

    def reset(self) -> None:
        self.state.reset()

    def ask(self, question: str) -> Answer:
        self.turn += 1
        planned = plan(question, self.state, self.llm, self.store, self.aliases, self.max_hops)
        p = planned.plan
        evidence = retrieve(p, self.store, self.alerts, self.profile, self.index, self.aliases)
        g = gate(p, evidence)
        attach_context(evidence, g.nearest, self.alerts, self.store)
        log: dict = {}
        answer = generate(p, evidence, g, self.llm, self.store, self.aliases, log)
        answer.trace_id = f"{datetime.now():%Y%m%dT%H%M%S}_{self.turn}"

        self.state.update(question, answer.text, p.intent, p.entity_ids, evidence.paths, self.store)
        self.last_answer, self.last_evidence, self.last_plan = answer, evidence, p
        self.last_trace = {
            "trace_id": answer.trace_id, "question": question,
            "provider": self.llm.name, "model": getattr(self.llm, "model", None),
            "linker_hits": [asdict(h) for h in planned.link.hits], "candidate_ids": planned.candidates,
            "plan_method": planned.method, "plan_raw": planned.raw, "plan": p.model_dump(),
            "kept_paths": [path_to_dict(x) for x in evidence.paths],
            "evidence_alert_ids": sorted(evidence.alerts), "allowed_sources": sorted(evidence.allowed_sources),
            "gate": asdict(g),
            "prompt_messages": log.get("messages", []), "raw_outputs": log.get("raw_outputs", []),
            "validator_errors": log.get("validator_errors", []),
            "answer": {"text": answer.text, "citations": answer.citations, "method": answer.method,
                       "fallback": answer.fallback, "errors": answer.errors},
        }
        if self.trace_dir:
            write_trace(self.last_trace, self.trace_dir)
        return answer
