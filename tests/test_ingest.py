from connie_lite.graph.build import build_graph
from connie_lite.graph.ingest import (
    FOCAL_ID,
    build_alias_table,
    canonical,
    entity_name,
    load_corpus,
    node_id,
    node_type_for,
    slug,
)


def test_entity_name_handles_all_three_keys():
    assert entity_name({"entity_type": "COMPANY_FOCAL", "name": "Solstice Robotics"}) == "Solstice Robotics"
    assert entity_name({"entity_type": "MACRO_SENSITIVITY", "theme": "tariffs"}) == "tariffs"
    assert entity_name({"entity_type": "COMMODITY", "commodity_name": "rare earth magnets"}) == "rare earth magnets"


def test_entity_name_raises_without_name():
    import pytest

    with pytest.raises(ValueError):
        entity_name({"entity_type": "COMMODITY"})


def test_generic_customer_segment():
    assert node_type_for("COMPANY_CUSTOMER", "e-commerce fulfillment customers") == "Segment"
    assert node_type_for("COMPANY_CUSTOMER", "Northline Logistics") == "Company"
    profile, alerts = load_corpus()
    a01 = next(a for a in alerts if a.id == "a01")
    seg = next(e for e in a01.entities if e.raw_type == "COMPANY_CUSTOMER")
    assert seg.node_id == "segment:e-commerce-fulfillment-customers"


def test_alias_resolves_to_focal():
    profile, _ = load_corpus()
    aliases = build_alias_table(profile)
    for alias in ("Solstice", "solstice robotics", "SOLSTICE ROBOTICS"):
        assert node_id("Company", canonical(alias, aliases)) == FOCAL_ID
    assert FOCAL_ID == "company:solstice-robotics"


def test_slug():
    assert slug("Monterrey, Mexico") == "monterrey-mexico"
    assert slug("AI-driven automation") == "ai-driven-automation"


def test_regulation_subtype():
    _, alerts = load_corpus()
    a14 = next(a for a in alerts if a.id == "a14")
    assert a14.entities[0].attrs.get("subtype") == "regulation"


def test_empty_entity_alerts_skipped_from_graph():
    profile, alerts = load_corpus()
    assert len(alerts) == 28
    store = build_graph(profile, alerts)
    alert_nodes = store.nodes("Alert")
    for aid in ("a23", "a24", "a25", "a26"):
        assert f"alert:{aid}" not in alert_nodes
    assert "alert:a09" in alert_nodes
