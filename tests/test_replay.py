import pytest
from pydantic import BaseModel

from connie_lite.answer.llm import CacheMiss, ReplayCache, strict_schema


class Out(BaseModel):
    intent: str
    ids: list[str]
    term: str | None


class FakeClient:
    name = "fake"
    model = "fake-1"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        return schema(intent=f"call{self.calls}", ids=["a", "b"], term=None)

    def complete_text(self, system, messages):
        self.calls += 1
        return f"answer {self.calls} [a09]."


def test_record_then_replay_identical(tmp_path):
    rec = ReplayCache(FakeClient(), "record", tmp_path)
    j = rec.complete_json("sys", "user", Out)
    t = rec.complete_text("sys", [{"role": "user", "content": "q"}])

    inner = FakeClient()
    rep = ReplayCache(inner, "replay", tmp_path)
    assert rep.complete_json("sys", "user", Out) == j
    assert rep.complete_text("sys", [{"role": "user", "content": "q"}]) == t
    assert inner.calls == 0  # replay never calls the provider


def test_record_is_read_through(tmp_path):
    inner = FakeClient()
    rec = ReplayCache(inner, "record", tmp_path)
    first = rec.complete_text("sys", [{"role": "user", "content": "q"}])
    assert rec.complete_text("sys", [{"role": "user", "content": "q"}]) == first
    assert inner.calls == 1  # the first recording sticks


def test_replay_miss_raises(tmp_path):
    rep = ReplayCache(FakeClient(), "replay", tmp_path)
    with pytest.raises(CacheMiss):
        rep.complete_text("sys", [{"role": "user", "content": "never recorded"}])


def test_key_depends_on_inputs(tmp_path):
    rec = ReplayCache(FakeClient(), "record", tmp_path)
    rec.complete_text("sys", [{"role": "user", "content": "q1"}])
    rec.complete_text("sys", [{"role": "user", "content": "q2"}])
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_strict_schema_shape():
    js = strict_schema(Out)
    assert js["additionalProperties"] is False
    assert sorted(js["required"]) == ["ids", "intent", "term"]


# ---- LLM path through the full pipeline, with a scripted fake provider ---------------------
from connie_lite.assistant import Assistant  # noqa: E402
from connie_lite.config import Settings  # noqa: E402


class ScriptedLLM:
    """Plans like a model would; answers from a queue of scripted texts."""

    name = "fake"
    model = "fake-1"

    def __init__(self, plan: dict, answers: list[str]):
        self.plan, self.answers, self.text_calls = plan, list(answers), 0

    def complete_json(self, system, user, schema):
        return schema.model_validate(self.plan)

    def complete_text(self, system, messages):
        self.text_calls += 1
        return self.answers.pop(0)


PLAN_Q1 = {"intent": "SUPPLIER_RISK", "entity_ids": ["company:solstice-robotics"], "target_type": "Commodity",
           "target_term": None, "max_hops": 2, "resolved_question": "Which Solstice suppliers carry commodity risk?"}
GOOD = ("Ferrotech Alloys, a Solstice Robotics supplier, is exposed to rare earth magnets [PROFILE, a09]. "
        "The a09 alert text itself does not name Solstice Robotics [a09].")


def ask(profile, alerts, llm):
    a = Assistant(Settings(provider="anthropic", model="fake-1"), llm, profile, alerts, trace_dir=None)
    return a, a.ask("Which of Solstice's suppliers carry commodity risk, and which commodity?")


def test_llm_answer_valid_first_try(profile, alerts):
    llm = ScriptedLLM(PLAN_Q1, [GOOD])
    a, ans = ask(profile, alerts, llm)
    assert a.last_trace["plan_method"] == "llm"
    assert ans.method == "llm" and not ans.fallback and ans.text == GOOD
    assert llm.text_calls == 1


def test_llm_retry_after_validation_error(profile, alerts):
    llm = ScriptedLLM(PLAN_Q1, ["Quanta Sensing supplies magnets [a42].", GOOD])
    a, ans = ask(profile, alerts, llm)
    assert ans.method == "llm" and ans.text == GOOD
    assert llm.text_calls == 2
    assert a.last_trace["validator_errors"][0] and a.last_trace["validator_errors"][1] == []
    assert "failed validation" in a.last_trace["prompt_messages"][-1]["content"]


def test_llm_falls_back_to_template(profile, alerts):
    llm = ScriptedLLM(PLAN_Q1, ["Uncited claim.", "Still uncited."])
    _, ans = ask(profile, alerts, llm)
    assert ans.fallback and ans.method == "template"
    assert ans.text.startswith("(rule-based answer)")


def test_llm_plan_with_invented_id_rejected(profile, alerts):
    from pydantic import ValidationError

    bad = dict(PLAN_Q1, entity_ids=["company:made-up"])
    with pytest.raises(ValidationError):
        ask(profile, alerts, ScriptedLLM(bad, [GOOD]))
