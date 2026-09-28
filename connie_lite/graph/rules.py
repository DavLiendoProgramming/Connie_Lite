"""Edge rules: how annotated alerts + the client profile become typed, source-backed edges.

ADD A RELATION HERE: write a small rule function and register it in EDGE_RULES.
Every edge carries one Support per source (alert id or PROFILE) with a provenance label, so any
edge can be traced back to the text or annotation that produced it.
"""
from __future__ import annotations

import re
from typing import Callable

from ..schema import PROFILE_SOURCE, Alert, Entity, Support
from .ingest import (
    PROFILE_LIST_TYPES,
    build_alias_table,
    canonical,
    focal_aliases,
    focal_id,
    node_id,
)
from .store import NetworkxStore

# ---- relation names --------------------------------------------------------
HAS_SUPPLIER = "HAS_SUPPLIER"
HAS_CUSTOMER = "HAS_CUSTOMER"
COMPETES_WITH = "COMPETES_WITH"
OPERATES_IN = "OPERATES_IN"
EXPOSED_TO = "EXPOSED_TO"
PRESENT_IN = "PRESENT_IN"
SUBJECT_TO = "SUBJECT_TO"
AFFECTS = "AFFECTS"
RELATED_TO = "RELATED_TO"
HAS_SITE = "HAS_SITE"
LOCATED_IN = "LOCATED_IN"
HAS_EXECUTIVE = "HAS_EXECUTIVE"

ROLE_RELS = {"COMPANY_SUPPLIER": HAS_SUPPLIER, "COMPANY_CUSTOMER": HAS_CUSTOMER, "COMPANY_COMPETITOR": COMPETES_WITH}
PROFILE_RELS = {
    "suppliers": HAS_SUPPLIER,
    "customers": HAS_CUSTOMER,
    "competitors": COMPETES_WITH,
    "key_markets": OPERATES_IN,
    "commodities": EXPOSED_TO,
    "geo_markets": PRESENT_IN,
    "regulators": SUBJECT_TO,
    "macro_sensitivities": EXPOSED_TO,
    "themes": EXPOSED_TO,
}
# attribute node type -> relation from the alert's subject company (R3)
ATTRIBUTE_RELS = {"Market": OPERATES_IN, "Commodity": EXPOSED_TO, "Country": PRESENT_IN, "Theme": EXPOSED_TO, "Regulator": SUBJECT_TO}
# (source type, target type) bridge edges for alerts with no company (R4)
CONTEXT_RELS = {
    ("Regulator", "Country"): AFFECTS,
    ("Regulator", "Market"): AFFECTS,
    ("Regulator", "Theme"): AFFECTS,
    ("Commodity", "Market"): AFFECTS,
    ("Theme", "Market"): AFFECTS,
}


def _support(provenance: str, alert: Alert | None) -> Support:
    if alert is None:
        return Support("profile", PROFILE_SOURCE, None)
    return Support(provenance, alert.id, alert.date)


def _focal(profile: dict) -> str:
    return focal_id(profile)


def names_focal(alert: Alert, profile: dict) -> bool:
    """Alert text names the client (focal entity annotated, or an alias appears as a whole word)."""
    if any(e.raw_type == "COMPANY_FOCAL" for e in alert.entities):
        return True
    pattern = r"\b(" + "|".join(re.escape(a) for a in focal_aliases(profile)) + r")\b"
    return re.search(pattern, alert.body, flags=re.IGNORECASE) is not None


def _text_or_annotation(alert: Alert, profile: dict) -> str:
    return "text" if names_focal(alert, profile) else "annotation"


def _of_type(alert: Alert, *node_types: str) -> list[Entity]:
    return [e for e in alert.entities if e.node_type in node_types]


# ---- rules -----------------------------------------------------------------
def rule_focal_role(store: NetworkxStore, profile: dict, alert: Alert) -> None:
    """R1: annotated supplier/customer/competitor role -> focal relation edge."""
    prov = _text_or_annotation(alert, profile)
    for e in alert.entities:
        if e.raw_type in ROLE_RELS and e.node_type == "Company" and "related_to_focal" in e.attrs:
            store.add_support(_focal(profile), ROLE_RELS[e.raw_type], e.node_id, _support(prov, alert))


def rule_profile(store: NetworkxStore, profile: dict, alert: None) -> None:
    """R2: every profile list item becomes a confirmed focal edge."""
    aliases = build_alias_table(profile)
    for key, rel in PROFILE_RELS.items():
        node_type = PROFILE_LIST_TYPES[key]
        for item in profile.get(key, []):
            name = canonical(item, aliases)
            nid = node_id(node_type, name)
            attrs = {"subtype": "regulation"} if node_type == "Regulator" and re.search(r"\bAct\b", name) else {}
            store.add_node(nid, node_type, name, **attrs)
            store.add_support(_focal(profile), rel, nid, _support("profile", None))


def rule_attribute(store: NetworkxStore, profile: dict, alert: Alert) -> None:
    """R3: attach an alert's attribute entities to its subject company (co-mention)."""
    companies = _of_type(alert, "Company")
    if not companies:
        return
    focal = _focal(profile)
    non_focal = sorted({e.node_id for e in companies if e.node_id != focal})
    subjects = non_focal or [focal]
    for e in alert.entities:
        rel = ATTRIBUTE_RELS.get(e.node_type)
        if rel is None:
            continue  # Company, Segment, Person, Site handled elsewhere / skipped
        for s in subjects:
            store.add_support(s, rel, e.node_id, _support("co_mention", alert))


def rule_context(store: NetworkxStore, profile: dict, alert: Alert) -> None:
    """R4: alerts without companies bridge regulators/commodities/themes to what they affect."""
    if _of_type(alert, "Company"):
        return
    ents = sorted({e.node_id: e for e in alert.entities}.values(), key=lambda e: e.node_id)
    for a in ents:
        for b in ents:
            rel = CONTEXT_RELS.get((a.node_type, b.node_type))
            if rel:
                store.add_support(a.node_id, rel, b.node_id, _support("co_mention", alert))
    themes = [e.node_id for e in ents if e.node_type == "Theme"]
    for i, a in enumerate(themes):
        for b in themes[i + 1:]:
            store.add_support(min(a, b), RELATED_TO, max(a, b), _support("co_mention", alert))


def rule_site(store: NetworkxStore, profile: dict, alert: Alert) -> None:
    """R5: manufacturing site -> focal HAS_SITE, and site LOCATED_IN the country after the last comma."""
    aliases = build_alias_table(profile)
    for e in _of_type(alert, "Site"):
        store.add_support(_focal(profile), HAS_SITE, e.node_id, _support(_text_or_annotation(alert, profile), alert))
        if "," in e.name:
            country = canonical(e.name.rsplit(",", 1)[1].strip(), aliases)
            cid = node_id("Country", country)
            store.add_node(cid, "Country", country)
            store.add_support(e.node_id, LOCATED_IN, cid, _support("text", alert))


def rule_executive(store: NetworkxStore, profile: dict, alert: Alert) -> None:
    """R6: executive -> focal HAS_EXECUTIVE with the role on the edge."""
    for e in _of_type(alert, "Person"):
        store.add_support(
            _focal(profile), HAS_EXECUTIVE, e.node_id, _support(_text_or_annotation(alert, profile), alert),
            role=e.attrs.get("role"),
        )


RuleFn = Callable[[NetworkxStore, dict, Alert | None], None]
# (name, scope, fn): scope "alert" runs once per alert with entities, "once" runs a single time.
EDGE_RULES: list[tuple[str, str, RuleFn]] = [
    ("R1_focal_role", "alert", rule_focal_role),
    ("R2_profile", "once", rule_profile),
    ("R3_attribute", "alert", rule_attribute),
    ("R4_context", "alert", rule_context),
    ("R5_site", "alert", rule_site),
    ("R6_executive", "alert", rule_executive),
]
