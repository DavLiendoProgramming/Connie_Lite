"""Generic graph traversals: they answer any question about the entities it mentions.

  NEIGHBORHOOD  walk 1..max_hops out from an entity (optionally one relation, or executives by role)
  CONNECT       bounded paths from an entity to a target node, or between two entities
Plus the shared machinery the templates use: the typed metapath matcher and target narrowing.
Nothing ever routes *through* the client hub (hub-routing guard).
"""
from __future__ import annotations

from itertools import combinations

from rapidfuzz import fuzz

from ..graph.ingest import FOCAL_ID
from ..graph.rules import (
    COMPETES_WITH,
    EXPOSED_TO,
    HAS_CUSTOMER,
    HAS_EXECUTIVE,
    HAS_SITE,
    HAS_SUPPLIER,
    OPERATES_IN,
    PRESENT_IN,
    SUBJECT_TO,
)
from ..graph.store import NetworkxStore
from ..schema import EdgeView
from .linker import link

TERM_TEXT_MIN = 90     # rapidfuzz partial_ratio for a free-text target term found in an alert
FOCAL_STEP = "FOCAL"   # template step node_type meaning "must be the client node"
HUB = {FOCAL_ID}       # hub-routing guard: traversals never pass *through* the client

# question keyword -> relation it asks about (NEIGHBORHOOD filter)
REL_KEYWORDS: dict[str, str] = {
    "supplier": HAS_SUPPLIER, "suppliers": HAS_SUPPLIER,
    "customer": HAS_CUSTOMER, "customers": HAS_CUSTOMER,
    "competitor": COMPETES_WITH, "competitors": COMPETES_WITH,
    "market": OPERATES_IN, "markets": OPERATES_IN,
    "commodity": EXPOSED_TO, "commodities": EXPOSED_TO,
    "country": PRESENT_IN, "countries": PRESENT_IN,
    "regulator": SUBJECT_TO, "regulators": SUBJECT_TO,
    "executive": HAS_EXECUTIVE, "executives": HAS_EXECUTIVE,
    "site": HAS_SITE, "sites": HAS_SITE, "plant": HAS_SITE, "plants": HAS_SITE,
}
TERM_SYNONYMS = {"tariff": "tariffs", "interest rate": "interest rates", "rates": "interest rates"}

# ---- path matching ---------------------------------------------------------------
def match_template(store: NetworkxStore, start_id: str, steps: list[tuple[str, str, str]]) -> list[list[EdgeView]]:
    out: list[list[EdgeView]] = []

    def dfs(node: str, i: int, edges: list[EdgeView], visited: frozenset[str]) -> None:
        if i == len(steps):
            out.append(edges)
            return
        rel, direction, node_type = steps[i]
        candidates = store.edges_from(node, rel) if direction == "out" else store.edges_to(node, rel)
        for e in candidates:
            nxt = e.dst if direction == "out" else e.src
            if node_type == FOCAL_STEP:
                ok = nxt == FOCAL_ID
            else:
                ok = nxt not in visited and store.type(nxt) == node_type
            if ok:
                dfs(nxt, i + 1, edges + [e], visited | {nxt})

    dfs(start_id, 0, [], frozenset({start_id}))
    return sorted(out, key=lambda es: tuple(e.id for e in es))


TARGET_NODE_TYPES = ("Commodity", "Theme", "Regulator", "Country", "Market", "Person", "Site")


def resolve_term(term: str | None, store: NetworkxStore, aliases: dict[str, str]) -> str | None:
    """Free-text target term -> non-company node id, via synonyms and the linker."""
    if not term:
        return None
    term = TERM_SYNONYMS.get(term.casefold().strip(), term)
    hits = [h for h in link(term, store, aliases).hits if store.type(h.node_id) in TARGET_NODE_TYPES]
    return hits[0].node_id if hits else None


# ---- finders: each returns (paths as edge lists, resolved target node or None) ----
Found = tuple[list[list[EdgeView]], str | None]


def find_neighborhood(plan, store, aliases, alerts) -> Found:
    """Walk 1..max_hops from each entity, or only its executives (by role) / one relation ("suppliers").
    Any other target term that reached here did not resolve to a node: no paths, so the gate reports it missing."""
    term = (plan.target_term or "").casefold()
    paths: list[list[EdgeView]] = []
    for ent in plan.entity_ids:
        if plan.target_type == "Person":
            paths += [[e] for e in store.semantic_edges(ent)
                      if e.rel == HAS_EXECUTIVE and (not term or e.attrs.get("role", "").casefold() == term)]
        elif term in REL_KEYWORDS:
            paths += [[e] for e in store.semantic_edges(ent) if e.rel == REL_KEYWORDS[term]]
        elif not term:
            paths += store.walk(ent, plan.max_hops, HUB)
    return paths, None


def find_connect(plan, store, aliases, alerts) -> Found:
    """Bounded paths from each entity to the target term's node, or between entity pairs when there is no target."""
    target = resolve_term(plan.target_term, store, aliases)
    if plan.target_term and not target:
        return [], None
    pairs = [(e, target) for e in plan.entity_ids if e != target] if target else list(combinations(plan.entity_ids, 2))
    return [p for a, b in pairs for p in store.simple_paths(a, b, plan.max_hops, HUB)], target


# 2. named metapath templates
def term_in_text(term: str, texts: list[str]) -> bool:
    """Fuzzy phrase match ("export controls" ~ "export control rules")."""
    return any(fuzz.partial_ratio(term.casefold(), t.casefold()) >= TERM_TEXT_MIN for t in texts)


def narrow_to_target(raw: list[list[EdgeView]], plan, store, aliases, alerts) -> Found:
    """Keep template matches that reach the target: a graph node if the term resolves to one,
    else paths whose final edge rests on alert text mentioning the term."""
    if not plan.target_term:
        return raw, None
    target = resolve_term(plan.target_term, store, aliases)
    if target:
        return [p for p in raw if any(target in (e.src, e.dst) for e in p)], target
    return [p for p in raw if term_in_text(plan.target_term, [alerts[s.source].text for s in p[-1].alert_supports])], None
