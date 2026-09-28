"""Load the profile and alerts, normalise inconsistent entity records into typed, canonical Entities."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..schema import Alert, Entity

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PACKAGE_ROOT / "data"

# raw entity_type -> graph node type. Company roles are refined by node_type_for().
NODE_TYPES: dict[str, str] = {
    "COMPANY_FOCAL": "Company",
    "COMPANY_SUPPLIER": "Company",
    "COMPANY_CUSTOMER": "Company",
    "COMPANY_COMPETITOR": "Company",
    "END_MARKET": "Market",
    "COMMODITY": "Commodity",
    "REGULATOR": "Regulator",
    "GEO_COUNTRY": "Country",
    "GEO_MANUFACTURING": "Site",
    "MACRO_SENSITIVITY": "Theme",
    "PERSON_EXECUTIVE": "Person",
}

# profile list key -> node type of its items
PROFILE_LIST_TYPES: dict[str, str] = {
    "competitors": "Company",
    "suppliers": "Company",
    "customers": "Company",
    "geo_markets": "Country",
    "key_markets": "Market",
    "commodities": "Commodity",
    "regulators": "Regulator",
    "macro_sensitivities": "Theme",
    "themes": "Theme",
}


def load_profile(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def entity_name(e: dict) -> str:
    name = e.get("name") or e.get("theme") or e.get("commodity_name")
    if not name:
        raise ValueError(f"entity has no name/theme/commodity_name: {e}")
    return name


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def node_type_for(raw_type: str, name: str) -> str:
    if raw_type not in NODE_TYPES:
        raise ValueError(f"unknown entity_type {raw_type!r}")
    node_type = NODE_TYPES[raw_type]
    # Lower-case "company" names are generic segments, e.g. "e-commerce fulfillment customers".
    if node_type == "Company" and name[:1].islower():
        return "Segment"
    return node_type


def node_id(node_type: str, canonical_name: str) -> str:
    return f"{node_type.lower()}:{slug(canonical_name)}"


def build_alias_table(profile: dict) -> dict[str, str]:
    """casefolded alias -> canonical name."""
    table: dict[str, str] = {}
    for key in PROFILE_LIST_TYPES:
        for item in profile.get(key, []):
            table[item.casefold()] = item
    table[profile["client_name"].casefold()] = profile["client_name"]
    for alias in profile.get("focal_companies", []):
        table[alias.casefold()] = profile["client_name"]
    return table


def canonical(name: str, aliases: dict[str, str]) -> str:
    return aliases.get(name.casefold(), name)


def focal_id(profile: dict) -> str:
    return node_id("Company", profile["client_name"])


def focal_aliases(profile: dict) -> list[str]:
    return sorted({profile["client_name"], *profile.get("focal_companies", [])})


def parse_entity(e: dict, aliases: dict[str, str]) -> Entity:
    raw_name = entity_name(e)
    raw_type = e["entity_type"]
    node_type = node_type_for(raw_type, raw_name)
    name = canonical(raw_name, aliases)
    attrs: dict = {}
    if "role" in e:
        attrs["role"] = e["role"]
    if "related_to_focal" in e:
        attrs["related_to_focal"] = e["related_to_focal"]
    if node_type == "Regulator" and re.search(r"\bAct\b", name):
        attrs["subtype"] = "regulation"
    return Entity(raw_type=raw_type, name=name, node_type=node_type, node_id=node_id(node_type, name), attrs=attrs)


def load_alerts(path: str | Path, aliases: dict[str, str] | None = None) -> list[Alert]:
    if aliases is None:
        aliases = build_alias_table(load_profile(Path(path).parent / "client_profile.json"))
    alerts = []
    for raw in json.loads(Path(path).read_text()):
        alerts.append(
            Alert(
                id=raw["id"],
                received_at=datetime.fromisoformat(raw["received_at"]),
                subject=raw["subject"],
                body=raw["body"],
                entities=tuple(parse_entity(e, aliases) for e in raw.get("entities", [])),
            )
        )
    return sorted(alerts, key=lambda a: a.id)


def load_corpus(data_dir: str | Path = DEFAULT_DATA_DIR) -> tuple[dict, list[Alert]]:
    data_dir = Path(data_dir)
    profile = load_profile(data_dir / "client_profile.json")
    return profile, load_alerts(data_dir / "sample_alerts_annotated.json", build_alias_table(profile))


FOCAL_ID = focal_id(load_profile(DEFAULT_DATA_DIR / "client_profile.json"))
