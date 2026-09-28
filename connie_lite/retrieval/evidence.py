"""Plan -> Evidence: run the finder for the plan's intent, score and keep the best paths, then attach
the alert text behind every kept edge. The LLM never retrieves: every path comes from graph edges,
and every alert from those edges' supports.
"""
from __future__ import annotations

from datetime import date

from ..graph.ingest import FOCAL_ID
from ..graph.rules import (
    COMPETES_WITH,
    EXPOSED_TO,
    HAS_CUSTOMER,
    HAS_SUPPLIER,
    OPERATES_IN,
    PRESENT_IN,
    SUBJECT_TO,
)
from ..graph.store import MENTIONS, NetworkxStore
from ..schema import PROFILE_SOURCE, Alert, EdgeView, Evidence, Path
from .templates import TEMPLATE_FINDERS
from .text_index import BM25_MIN, BM25_TOP, AlertIndex
from .traversals import find_connect, find_neighborhood

K_PATHS = 8          # at most 8 paths, so at most ~8 supporting alerts reach the prompt
RECENCY_HALF_LIFE_DAYS = 60

# intent -> finder. Generic traversals first, then the named templates.
FINDERS = {"NEIGHBORHOOD": find_neighborhood, "CONNECT": find_connect, **TEMPLATE_FINDERS}


# ---- scoring -----------------------------------------------------------------------
def score_path(edges: list[EdgeView], ref_date: date) -> float:
    conf = 1.0
    for e in edges:
        conf *= e.confidence
    dates = [e.last_seen for e in edges if e.last_seen is not None]
    recency = 0.5 ** ((ref_date - max(dates)).days / RECENCY_HALF_LIFE_DAYS) if dates else 1.0
    return round(conf * recency, 6)


def rank_paths(raw: list[list[EdgeView]], ref_date: date, k: int = K_PATHS) -> list[Path]:
    unique = {tuple(e.id for e in es): es for es in raw}
    paths = [Path(tuple(es), score_path(es, ref_date)) for es in unique.values()]
    return sorted(paths, key=lambda p: (-p.score, p.edge_ids))[:k]


# ---- evidence assembly ---------------------------------------------------------------
PROFILE_FACT = {
    HAS_SUPPLIER: "Client profile lists {dst} as a supplier of {src}.",
    HAS_CUSTOMER: "Client profile lists {dst} as a customer of {src}.",
    COMPETES_WITH: "Client profile lists {dst} as a competitor of {src}.",
    OPERATES_IN: "Client profile lists {dst} as a key market of {src}.",
    EXPOSED_TO: "Client profile lists {dst} as an exposure of {src}.",
    PRESENT_IN: "Client profile lists {dst} as a geographic market of {src}.",
    SUBJECT_TO: "Client profile lists {dst} as a regulator relevant to {src}.",
}


def profile_fact(e: EdgeView, store: NetworkxStore) -> str:
    tmpl = PROFILE_FACT.get(e.rel, "Client profile links {src} and {dst} ({rel}).")
    return tmpl.format(src=store.name(e.src), dst=store.name(e.dst), rel=e.rel)


def alert_ids_of(paths: list[Path]) -> list[str]:
    return sorted({s.source for p in paths for e in p.edges for s in e.alert_supports})


def mentioned_nodes(alert_ids, store: NetworkxStore) -> set[str]:
    out: set[str] = set()
    for aid in alert_ids:
        if store.has_node(f"alert:{aid}"):
            out |= {e.dst for e in store.edges_from(f"alert:{aid}", MENTIONS)}
    return out


def related_context(plan, paths: list[Path], store: NetworkxStore, scores: dict[str, float]) -> list[str]:
    """'Closest related evidence' for partial answers: alerts behind the query entities' own edges
    (never via the client hub), or any alert when no entity was found, that also match the question text."""
    if plan.entity_ids:
        edges = [e for ent in plan.entity_ids for e in store.semantic_edges(ent) if ent == FOCAL_ID or e.other(ent) != FOCAL_ID]
        ids = {s.source for e in edges for s in e.alert_supports}
    else:
        ids = set(scores)
    ids -= set(alert_ids_of(paths))
    return sorted((i for i in ids if scores.get(i, 0.0) >= BM25_MIN), key=lambda i: (-scores[i], i))


def retrieve(plan, store: NetworkxStore, alerts: dict[str, Alert], profile: dict, bm25: AlertIndex,
             aliases: dict[str, str]) -> Evidence:
    raw, target_id = FINDERS[plan.intent](plan, store, aliases, alerts)
    paths = rank_paths(raw, max(a.date for a in alerts.values()))
    scores = bm25.scores(plan.resolved_question)
    alert_ids = alert_ids_of(paths)

    facts: list[str] = []
    for p in paths:
        for e in p.edges:
            if e.status == "confirmed" and (f := profile_fact(e, store)) not in facts:
                facts.append(f)

    nodes = {n for p in paths for n in p.nodes} | set(plan.entity_ids) | ({target_id} if target_id else set())
    return Evidence(
        paths=paths,
        alerts={i: alerts[i] for i in alert_ids},
        profile_facts=facts,
        allowed_sources=set(alert_ids) | ({PROFILE_SOURCE} if facts else set()),
        subgraph_nodes=nodes | mentioned_nodes(alert_ids, store),
        related_context=related_context(plan, paths, store, scores),
        target_id=target_id,
        bm25_top=sorted(((i, s) for i, s in scores.items() if s > 0), key=lambda kv: (-kv[1], kv[0]))[:BM25_TOP],
    )


def attach_context(evidence: Evidence, alert_ids: list[str], alerts: dict[str, Alert], store: NetworkxStore) -> None:
    """Add 'nearest' alerts to the evidence so the answer may cite them."""
    for aid in alert_ids:
        evidence.alerts.setdefault(aid, alerts[aid])
        evidence.allowed_sources.add(aid)
    evidence.subgraph_nodes |= mentioned_nodes(alert_ids, store)
