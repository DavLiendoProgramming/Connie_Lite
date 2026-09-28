"""Named multi-hop question types, as typed metapath templates over the graph.

ADD A QUESTION TYPE HERE:
  1. add the typed chain to TEMPLATES
  2. add a finder (usually: match_template + narrow_to_target) and register it in TEMPLATE_FINDERS
  3. teach the planner: a keyword rule in rule_plan() and one line in PLANNER_SYSTEM (planner.py)
The intent name becomes valid in the plan schema automatically.
"""
from __future__ import annotations

from ..graph.ingest import FOCAL_ID
from ..graph.rules import (
    AFFECTS,
    COMPETES_WITH,
    EXPOSED_TO,
    HAS_CUSTOMER,
    HAS_SUPPLIER,
    OPERATES_IN,
    PRESENT_IN,
)
from ..schema import EdgeView
from .traversals import FOCAL_STEP, Found, match_template, narrow_to_target

# Metapath templates: (relation, direction, node type of the next node).
TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "SUPPLIER_COMMODITY": [(HAS_SUPPLIER, "out", "Company"), (EXPOSED_TO, "out", "Commodity")],
    "SUPPLIER_REGULATOR": [(HAS_SUPPLIER, "out", "Company"), (PRESENT_IN, "out", "Country"), (AFFECTS, "in", "Regulator")],
    "SHARED_MARKET": [
        (COMPETES_WITH, "out", "Company"), (OPERATES_IN, "out", "Market"),
        (OPERATES_IN, "in", "Company"), (HAS_CUSTOMER, "in", FOCAL_STEP),
    ],
}
DISCOVERED_RELS = (HAS_SUPPLIER, HAS_CUSTOMER, COMPETES_WITH)


def is_focal_relationship(e: EdgeView) -> bool:
    """Client -> supplier / customer / competitor edge (the edges that can be 'newly discovered')."""
    return e.src == FOCAL_ID and e.rel in DISCOVERED_RELS


def supplier_risk_templates(plan) -> list[str]:
    """Commodity target: 2-hop template. Regulator target: 3-hop template. Otherwise both, if hops allow."""
    if plan.target_type == "Commodity":
        return ["SUPPLIER_COMMODITY"]
    if plan.target_type == "Regulator":
        return ["SUPPLIER_REGULATOR"]
    return ["SUPPLIER_COMMODITY"] + (["SUPPLIER_REGULATOR"] if plan.max_hops >= 3 else [])


def find_supplier_risk(plan, store, aliases, alerts) -> Found:
    raw = [p for name in supplier_risk_templates(plan) for p in match_template(store, FOCAL_ID, TEMPLATES[name])]
    return narrow_to_target(raw, plan, store, aliases, alerts)


def find_shared_market(plan, store, aliases, alerts) -> Found:
    return narrow_to_target(match_template(store, FOCAL_ID, TEMPLATES["SHARED_MARKET"]), plan, store, aliases, alerts)


def find_discovered(plan, store, aliases, alerts) -> Found:
    raw = [[e] for e in store.edges_from(FOCAL_ID) if e.rel in DISCOVERED_RELS and e.status == "discovered"]
    return narrow_to_target(raw, plan, store, aliases, alerts)


TEMPLATE_FINDERS = {
    "SUPPLIER_RISK": find_supplier_risk,
    "SHARED_MARKET": find_shared_market,
    "DISCOVERED": find_discovered,
}
