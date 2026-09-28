import pytest

from connie_lite.answer.validate import citations, split_sentences, validate
from connie_lite.schema import Evidence


@pytest.fixture()
def evidence():
    return Evidence(
        paths=[], alerts={}, profile_facts=[],
        allowed_sources={"a09", "PROFILE"},
        subgraph_nodes={"company:solstice-robotics", "company:ferrotech-alloys", "commodity:rare-earth-magnets"},
    )


def check(text, evidence, store, aliases):
    return validate(text, evidence, store, aliases)


def test_accepts_grounded_answer(evidence, store, aliases):
    text = "Ferrotech Alloys supplies Solstice Robotics [PROFILE, a09]. It is exposed to rare earth magnets [a09]."
    assert check(text, evidence, store, aliases) == []


def test_rejects_unknown_id(evidence, store, aliases):
    errors = check("Ferrotech Alloys is exposed to rare earth magnets [a99].", evidence, store, aliases)
    assert any("a99" in e for e in errors)


def test_rejects_uncited_sentence(evidence, store, aliases):
    errors = check("Ferrotech Alloys is exposed to rare earth magnets [a09]. Prices will keep rising.", evidence, store, aliases)
    assert any("without citation" in e for e in errors)


def test_rejects_company_outside_subgraph(evidence, store, aliases):
    errors = check("Quanta Sensing also supplies rare earth magnets [a09].", evidence, store, aliases)
    assert any("Quanta Sensing" in e for e in errors)


def test_accepts_not_found_without_citation(evidence, store, aliases):
    text = "Not found: no evidence links Ferrotech Alloys to tariffs. Ferrotech Alloys faces magnet price pressure [a09]."
    assert check(text, evidence, store, aliases) == []


def test_period_inside_citation_does_not_split():
    assert split_sentences("One fact [a09. PROFILE]. Two [a09].") == ["One fact [a09. PROFILE].", "Two [a09]."]


def test_citation_parsing():
    assert citations("x [a09, PROFILE]. y [a10]") == ["a09", "PROFILE", "a10"]


def test_rule_label_ignored(evidence, store, aliases):
    assert check("(rule-based answer)\nFerrotech Alloys [a09].", evidence, store, aliases) == []


def test_requires_honesty_labels(store, aliases, alerts):
    from connie_lite.retrieval.evidence import retrieve
    from connie_lite.retrieval.planner import make_plan_model
    from connie_lite.retrieval.text_index import AlertIndex

    focal = "company:solstice-robotics"
    plan = make_plan_model([focal])(intent="DISCOVERED", entity_ids=[focal], target_type=None, target_term=None,
                                    max_hops=2, resolved_question="new relationships")
    ev = retrieve(plan, store, {a.id: a for a in alerts}, {}, AlertIndex(alerts), aliases)
    bare = "Hanley Precision Casting supplies Solstice Robotics [a21]."
    assert any("newly discovered" in e for e in validate(bare, ev, store, aliases))
    ok = "Hanley Precision Casting is a newly discovered supplier, not in the client profile [a21]."
    assert validate(ok, ev, store, aliases) == []

    plan = make_plan_model([focal])(intent="SUPPLIER_RISK", entity_ids=[focal], target_type="Commodity", target_term=None,
                                    max_hops=2, resolved_question="supplier commodity risk")
    ev = retrieve(plan, store, {a.id: a for a in alerts}, {}, AlertIndex(alerts), aliases)
    bare = "Ferrotech Alloys is exposed to rare earth magnets [PROFILE, a09]."
    assert any("does not name" in e for e in validate(bare, ev, store, aliases))
    ok = bare + " The a09 alert text itself does not name Solstice Robotics [a09]."
    assert validate(ok, ev, store, aliases) == []
