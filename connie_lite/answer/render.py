"""Deterministic extractive answer (no LLM): one sentence per kept edge, a quote from each supporting
alert, honesty labels, "Not found:" for missing parts. Also the fallback when an LLM answer fails validation."""
from __future__ import annotations

import re

from ..graph.ingest import FOCAL_ID
from ..graph.rules import (
    AFFECTS,
    COMPETES_WITH,
    EXPOSED_TO,
    HAS_CUSTOMER,
    HAS_EXECUTIVE,
    HAS_SITE,
    HAS_SUPPLIER,
    LOCATED_IN,
    OPERATES_IN,
    PRESENT_IN,
    RELATED_TO,
    SUBJECT_TO,
)
from ..graph.store import NetworkxStore
from ..retrieval.gate import ABSTENTION, GateResult
from ..retrieval.templates import is_focal_relationship
from ..schema import Alert, EdgeView, Evidence
from .validate import NOT_FOUND, RULE_LABEL

DISCOVERED_NOTE = "newly discovered, not in the client profile"
REL_PHRASE = {
    HAS_SUPPLIER: "{dst} is a supplier to {src}",
    HAS_CUSTOMER: "{dst} is a customer of {src}",
    COMPETES_WITH: "{dst} is a competitor of {src}",
    OPERATES_IN: "{src} operates in {dst}",
    EXPOSED_TO: "{src} is exposed to {dst}",
    PRESENT_IN: "{src} has a presence in {dst}",
    SUBJECT_TO: "{src} is subject to {dst}",
    AFFECTS: "{src} is reported as affecting {dst}",
    RELATED_TO: "{src} is discussed together with {dst}",
    HAS_SITE: "{src} has a manufacturing site in {dst}",
    LOCATED_IN: "{src} is located in {dst}",
    HAS_EXECUTIVE: "{dst} is the {role} of {src}",
}

# ---- shared helpers ---------------------------------------------------------------
def split_body(body: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", body) if s.strip()]


def best_sentence(alert: Alert, names: list[str]) -> str:
    """The body sentence naming the most of `names`; ties go to the earlier sentence."""
    sentences = split_body(alert.body)
    hits = [sum(n.casefold() in s.casefold() for n in names) for s in sentences]
    return sentences[hits.index(max(hits))]


def cite(ids) -> str:
    return "[" + ", ".join(ids) + "]"


def quote(alert: Alert, names: list[str]) -> str:
    return f'{alert.id} ({alert.date.isoformat()}): "{best_sentence(alert, names).rstrip(".")}" [{alert.id}].'


# ---- deterministic renderer --------------------------------------------------------
def edge_sentences(e: EdgeView, store: NetworkxStore, evidence: Evidence, quoted: set[str]) -> list[str]:
    ids = [s for s in e.sources if s in evidence.allowed_sources]
    if not ids:
        return []
    src, dst = store.name(e.src), store.name(e.dst)
    text = REL_PHRASE.get(e.rel, "{src} is linked to {dst} ({rel})").format(
        src=src, dst=dst, rel=e.rel, role=e.attrs.get("role") or "executive"
    )
    if is_focal_relationship(e) and e.status == "discovered":
        text += f" ({DISCOVERED_NOTE})"
    out = [f"{text} {cite(ids)}."]
    if is_focal_relationship(e) and e.annotation_only:
        alert_ids = [s.source for s in e.alert_supports if s.source in evidence.allowed_sources]
        if alert_ids:
            basis = "the entity annotation and the client profile" if e.status == "confirmed" else "the entity annotation"
            label = f"alert{'s' if len(alert_ids) > 1 else ''} {', '.join(alert_ids)}"
            out.append(f"The text of {label} does not name {src}; this link rests on {basis} {cite(ids)}.")
    for aid in [s.source for s in e.alert_supports]:
        if aid in evidence.alerts and aid not in quoted:
            quoted.add(aid)
            out.append(quote(evidence.alerts[aid], [dst, src]))
    return out


def not_found_sentence(missing: str, plan, store: NetworkxStore) -> str:
    names = " and ".join(store.name(e) for e in plan.entity_ids) or "the question"
    missing = re.sub(r"\b[a-z]+:[a-z0-9-]+\b", lambda m: store.name(m[0]) if store.has_node(m[0]) else m[0], missing)
    guard = " (routes through the client itself are not counted)" if plan.entity_ids and FOCAL_ID not in plan.entity_ids else ""
    return f'{NOT_FOUND} no evidence on "{missing}" for {names} in the alerts or client profile{guard}.'


def nearest_sentences(plan, evidence: Evidence, gate_result: GateResult, store: NetworkxStore) -> list[str]:
    names = [store.name(e) for e in plan.entity_ids] + ([plan.target_term] if plan.target_term else [])
    return [f"Closest related evidence: {quote(evidence.alerts[aid], names)}" for aid in gate_result.nearest if aid in evidence.alerts]


def render_template(plan, evidence: Evidence, gate_result: GateResult, store: NetworkxStore) -> str:
    """Deterministic extractive answer: one sentence per kept edge plus a quote from each supporting alert."""
    if gate_result.status == "none":
        return "\n".join([f"{NOT_FOUND} {ABSTENTION}", *nearest_sentences(plan, evidence, gate_result, store)])
    lines = [RULE_LABEL]
    seen_edges: set[str] = set()
    quoted: set[str] = set()
    for path in evidence.paths:
        for e in path.edges:
            if e.id not in seen_edges:
                seen_edges.add(e.id)
                lines += edge_sentences(e, store, evidence, quoted)
    lines += [not_found_sentence(m, plan, store) for m in gate_result.missing]
    lines += nearest_sentences(plan, evidence, gate_result, store)
    return "\n".join(lines)
