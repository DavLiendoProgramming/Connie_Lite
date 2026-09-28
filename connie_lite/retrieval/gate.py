"""Sufficiency gate: decide answerable / partial / none BEFORE any generation."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schema import Evidence
from .text_index import BM25_MIN

MAX_NEAREST = 2
ABSTENTION = "I don't have evidence in the alert corpus to answer that."
# What is reported missing when an intent's template finds nothing and no target term was asked.
MISSING_LABELS = {
    "NEIGHBORHOOD": "facts about the requested entity",
    "CONNECT": "a connection between the requested entities",
    "SUPPLIER_RISK": "risk reaching the client through its suppliers",
    "SHARED_MARKET": "competitors in the same end markets as the client's customers",
    "DISCOVERED": "relationships not already in the client profile",
}


@dataclass
class GateResult:
    status: str                              # "answerable" | "partial" | "none"
    missing: list[str] = field(default_factory=list)
    nearest: list[str] = field(default_factory=list)


def missing_parts(plan, evidence: Evidence) -> list[str]:
    if evidence.paths:
        if plan.intent == "CONNECT" and evidence.target_id:  # some entities may still lack a path to the target
            reached = {n for p in evidence.paths for n in p.nodes}
            return [f"{plan.target_term} ({e})" for e in plan.entity_ids if e not in reached]
        return []
    if plan.target_type == "Person":
        return [plan.target_term or "executive"]
    return [plan.target_term or MISSING_LABELS[plan.intent]]


def gate(plan, evidence: Evidence) -> GateResult:
    missing = missing_parts(plan, evidence)
    nearest = evidence.related_context[:MAX_NEAREST]
    if evidence.paths and not missing:
        return GateResult("answerable")
    best_bm25 = max((s for _, s in evidence.bm25_top), default=0.0)
    if not evidence.paths and best_bm25 < BM25_MIN:
        return GateResult("none", missing, nearest)
    return GateResult("partial", missing, nearest)
