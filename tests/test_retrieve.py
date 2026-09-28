import pytest

from connie_lite.retrieval.evidence import retrieve
from connie_lite.retrieval.planner import make_plan_model
from connie_lite.retrieval.templates import TEMPLATES
from connie_lite.retrieval.text_index import AlertIndex
from connie_lite.retrieval.traversals import match_template

FOCAL = "company:solstice-robotics"


@pytest.fixture(scope="module")
def ctx(profile, alerts, store, aliases):
    return {"store": store, "alerts": {a.id: a for a in alerts}, "profile": profile, "bm25": AlertIndex(alerts), "aliases": aliases}


def make_plan(intent, entity_ids, target_type=None, target_term=None, max_hops=2, q="q"):
    model = make_plan_model([FOCAL, *entity_ids])
    return model(intent=intent, entity_ids=entity_ids, target_type=target_type, target_term=target_term,
                 max_hops=max_hops, resolved_question=q)


def run(ctx, plan):
    return retrieve(plan, ctx["store"], ctx["alerts"], ctx["profile"], ctx["bm25"], ctx["aliases"])


def edge_triples(evidence):
    return [[(e.src, e.rel, e.dst) for e in p.edges] for p in evidence.paths]


def test_supplier_risk_ferrotech(ctx):
    ev = run(ctx, make_plan("SUPPLIER_RISK", [FOCAL], "Commodity", q="suppliers commodity risk"))
    assert edge_triples(ev) == [[
        (FOCAL, "HAS_SUPPLIER", "company:ferrotech-alloys"),
        ("company:ferrotech-alloys", "EXPOSED_TO", "commodity:rare-earth-magnets"),
    ]]
    assert set(ev.alerts) == {"a09"}
    assert ev.allowed_sources == {"a09", "PROFILE"}


def test_supplier_risk_three_hop_regulator(ctx):
    ev = run(ctx, make_plan("SUPPLIER_RISK", [FOCAL], "Regulator", max_hops=3, q="export controls supply chain"))
    assert [
        (FOCAL, "HAS_SUPPLIER", "company:delta-servo-corp"),
        ("company:delta-servo-corp", "PRESENT_IN", "country:south-korea"),
        ("regulator:us-department-of-commerce", "AFFECTS", "country:south-korea"),
    ] in edge_triples(ev)
    assert {"a10", "a13"} <= set(ev.alerts)


def test_exposure_hub_guard(ctx):
    """Ferrotech -> Solstice -> tariffs must NOT count as Ferrotech's tariff exposure."""
    ev = run(ctx, make_plan("CONNECT", ["company:ferrotech-alloys"], "Theme", "tariffs",
                            q="What is Ferrotech Alloys' exposure to tariffs?"))
    assert ev.paths == []
    assert ev.target_id == "theme:tariffs"
    assert ev.related_context[:1] == ["a09"]
    # without the guard a path through the focal hub exists
    assert ctx["store"].simple_paths("company:ferrotech-alloys", "theme:tariffs", 2, set())


def test_focal_exposure_allowed(ctx):
    ev = run(ctx, make_plan("CONNECT", [FOCAL], "Theme", "tariffs"))
    assert [(FOCAL, "EXPOSED_TO", "theme:tariffs")] in edge_triples(ev)


def test_shared_market(ctx):
    ev = run(ctx, make_plan("SHARED_MARKET", [FOCAL], q="competitors same end markets customers"))
    triples = {(p.edges[0].dst, p.edges[1].dst, p.edges[2].src) for p in ev.paths}
    for cust in ("northline-logistics", "bayview-fulfillment", "orion-freight-systems"):
        assert ("company:kestrel-automation", "market:warehouse-automation", f"company:{cust}") in triples
    assert all(len(p.edges) == 4 and p.edges[3].src == FOCAL for p in ev.paths)
    assert {"a04", "a05", "a12", "a22"} <= set(ev.alerts)


def test_discovered(ctx):
    ev = run(ctx, make_plan("DISCOVERED", [FOCAL]))
    assert sorted(p.edges[0].dst for p in ev.paths) == ["company:hanley-precision-casting", "company:orion-freight-systems"]


def test_ceo_not_found(ctx):
    ev = run(ctx, make_plan("NEIGHBORHOOD", [FOCAL], "Person", "CEO", q="Who is Solstice's CEO?"))
    assert ev.paths == []
    assert ev.related_context == ["a02"]
    ev = run(ctx, make_plan("NEIGHBORHOOD", [FOCAL], "Person", "CFO"))
    assert edge_triples(ev) == [[(FOCAL, "HAS_EXECUTIVE", "person:elena-marsh")]]


def test_template_match_is_typed(ctx):
    for path in match_template(ctx["store"], FOCAL, TEMPLATES["SUPPLIER_COMMODITY"]):
        assert ctx["store"].type(path[1].dst) == "Commodity"


def test_deterministic_order(ctx):
    plan = make_plan("SHARED_MARKET", [FOCAL], q="competitors same end markets customers")
    first = [p.edge_ids for p in run(ctx, plan).paths]
    for _ in range(3):
        assert [p.edge_ids for p in run(ctx, plan).paths] == first


def test_free_text_target_is_text_grounded(ctx):
    """A target term that is not a node filters paths by the supporting alert text."""
    ev = run(ctx, make_plan("SUPPLIER_RISK", [FOCAL], "Regulator", "export controls", max_hops=3))
    assert any(p.edges[-1].src == "regulator:us-department-of-commerce" for p in ev.paths)
    ev = run(ctx, make_plan("SUPPLIER_RISK", [FOCAL], "Commodity", "batteries"))
    assert ev.paths == []


def test_neighborhood_walks_two_hops_without_hub(ctx):
    ev = run(ctx, make_plan("NEIGHBORHOOD", ["company:kestrel-automation"]))
    assert any(len(p.edges) == 2 for p in ev.paths)          # 2-hop chains, e.g. Kestrel -> market <- customer
    assert all(p.edges[0].src != FOCAL or len(p.edges) == 1 for p in ev.paths)


def test_connect_two_entities(ctx):
    ev = run(ctx, make_plan("CONNECT", ["company:delta-servo-corp", "regulator:us-department-of-commerce"]))
    assert [("company:delta-servo-corp", "PRESENT_IN", "country:south-korea"),
            ("regulator:us-department-of-commerce", "AFFECTS", "country:south-korea")] in edge_triples(ev)


def test_generic_llm_target_term_is_dropped(store, aliases):
    from connie_lite.retrieval.linker import link
    from connie_lite.retrieval.planner import post_validate

    raw = {"intent": "SUPPLIER_RISK", "entity_ids": [FOCAL], "target_type": "Commodity", "target_term": "commodity risk",
           "max_hops": 2, "resolved_question": "q"}
    plan = post_validate(raw, store, link("q", store, aliases), [FOCAL], aliases)
    assert plan.target_term is None
