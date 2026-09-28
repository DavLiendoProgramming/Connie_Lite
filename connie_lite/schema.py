"""Core records. Frozen dataclasses internally; pydantic only for LLM-facing JSON (see planner.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Provenance = Literal["profile", "text", "annotation", "co_mention"]
PROVENANCE_WEIGHT: dict[str, float] = {"profile": 1.0, "text": 0.9, "annotation": 0.7, "co_mention": 0.6}
PROFILE_SOURCE = "PROFILE"


@dataclass(frozen=True)
class Entity:
    raw_type: str
    name: str          # canonical name
    node_type: str
    node_id: str
    attrs: dict = field(default_factory=dict, hash=False, compare=False)  # e.g. {"role": "CFO"}


@dataclass(frozen=True)
class Alert:
    id: str
    received_at: datetime
    subject: str
    body: str
    entities: tuple[Entity, ...]

    @property
    def date(self) -> date:
        return self.received_at.date()

    @property
    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass(frozen=True)
class Support:
    provenance: Provenance
    source: str            # alert id ("a09") or "PROFILE"
    date: date | None

    @property
    def sort_key(self) -> tuple:
        return (self.source, self.provenance)

    def label(self) -> str:
        return self.source if self.provenance == "profile" else f"{self.source}({self.provenance})"


@dataclass(frozen=True)
class EdgeView:
    src: str
    rel: str
    dst: str
    supports: tuple[Support, ...]
    attrs: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def id(self) -> str:
        return f"{self.src}-{self.rel}->{self.dst}"

    @property
    def status(self) -> str:
        return "confirmed" if any(s.provenance == "profile" for s in self.supports) else "discovered"

    @property
    def confidence(self) -> float:
        return max((PROVENANCE_WEIGHT[s.provenance] for s in self.supports), default=0.0)

    @property
    def last_seen(self) -> date | None:
        dates = [s.date for s in self.supports if s.date is not None]
        return max(dates) if dates else None

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(sorted({s.source for s in self.supports}))

    @property
    def alert_supports(self) -> tuple[Support, ...]:
        return tuple(s for s in self.supports if s.source != PROFILE_SOURCE)

    @property
    def annotation_only(self) -> bool:
        """True when every alert behind this edge links it only through annotation."""
        alert = self.alert_supports
        return bool(alert) and all(s.provenance == "annotation" for s in alert)

    def other(self, node_id: str) -> str:
        return self.dst if node_id == self.src else self.src


@dataclass(frozen=True)
class Path:
    edges: tuple[EdgeView, ...]
    score: float

    @property
    def edge_ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.edges)

    @property
    def nodes(self) -> tuple[str, ...]:
        seen: list[str] = []
        for e in self.edges:
            for n in (e.src, e.dst):
                if n not in seen:
                    seen.append(n)
        return tuple(seen)


@dataclass
class Evidence:
    paths: list[Path]
    alerts: dict[str, Alert]            # only alerts supporting chosen paths (+ bm25 / nearest extras)
    profile_facts: list[str]
    allowed_sources: set[str]           # alert ids + "PROFILE"
    subgraph_nodes: set[str]
    related_context: list[str] = field(default_factory=list)          # alert ids near the query entities
    target_id: str | None = None                                     # resolved target node, if any
    bm25_top: list[tuple[str, float]] = field(default_factory=list)  # (alert id, score), best first
