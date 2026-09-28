import pytest

from connie_lite.answer.llm import TemplateClient
from connie_lite.assistant import Assistant
from connie_lite.config import Settings


@pytest.fixture()
def assistant(profile, alerts):
    return Assistant(Settings(), TemplateClient(), profile, alerts, trace_dir=None)


def test_ceo_question_partial_with_cfo_nearest(assistant):
    ans = assistant.ask("Who is Solstice's CEO?")
    g = assistant.last_trace["gate"]
    assert g["status"] in ("partial", "none")
    assert g["missing"] == ["CEO"]
    assert g["nearest"][:1] == ["a02"]
    assert "Not found:" in ans.text and "[a02]" in ans.text


def test_tariff_follow_up_partial(assistant):
    assistant.ask("Which of Solstice's suppliers carry commodity risk, and which commodity?")
    assert assistant.last_trace["gate"]["status"] == "answerable"
    ans = assistant.ask("And what about their exposure to tariffs?")
    assert assistant.last_plan.entity_ids == ["company:ferrotech-alloys"]
    assert ans.gate_status == "partial"
    assert assistant.last_trace["gate"]["missing"] == ["tariffs"]
    assert "a09" in assistant.last_trace["gate"]["nearest"]


def test_off_topic_is_none_and_skips_generation(assistant):
    ans = assistant.ask("What is the weather in Paris?")
    assert ans.gate_status == "none"
    assert ans.method == "abstain"
    assert ans.text.startswith("Not found:")
