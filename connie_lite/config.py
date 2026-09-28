"""Runtime settings read from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HARD_MAX_HOPS = 4


@dataclass(frozen=True)
class Settings:
    provider: str = "template"      # "template" (no LLM) | "anthropic"
    model: str | None = None
    max_hops: int = 2
    replay_mode: str = "off"        # "off" | "record" | "replay"
    data_dir: Path = Path("data")


def clamp_hops(n) -> int:
    return max(1, min(int(n), HARD_MAX_HOPS))


def load_settings() -> Settings:
    provider = os.environ.get("LLM_PROVIDER", "template").lower()
    model = os.environ.get("LLM_MODEL") or None
    if provider not in ("template", "anthropic"):
        raise ValueError(f"LLM_PROVIDER must be 'template' or 'anthropic', got {provider!r}")
    if provider != "template" and not model:
        raise ValueError("LLM_MODEL is required when LLM_PROVIDER=anthropic")
    return Settings(
        provider=provider,
        model=model,
        max_hops=clamp_hops(os.environ.get("MAX_HOPS", 2)),
        replay_mode=os.environ.get("REPLAY_MODE") or ("off" if provider == "template" else "record"),
        data_dir=Path(os.environ.get("DATA_DIR") or "data"),
    )
