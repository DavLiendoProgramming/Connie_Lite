import importlib.util
from pathlib import Path

import pytest

from connie_lite.answer.llm import TemplateClient
from connie_lite.assistant import Assistant
from connie_lite.config import Settings

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("demo", ROOT / "scripts" / "demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

# per question: (strings that must appear, citations that must appear, allowed gate statuses)
EXPECTED = [
    (["Ferrotech Alloys", "rare earth magnets", "does not name Solstice"], ["a09", "PROFILE"], {"answerable"}),
    (["Not found:", "Ferrotech Alloys", "tariffs"], ["a09"], {"partial"}),
    (["Kestrel Automation", "warehouse automation", "Northline Logistics", "Bayview Fulfillment", "Orion Freight Systems",
      "newly discovered"], ["a05", "a04", "a12", "a22"], {"answerable"}),
    (["Hanley Precision Casting", "Orion Freight Systems", "newly discovered"], ["a21", "a22"], {"answerable"}),
    (["Delta Servo Corp", "South Korea", "US Department of Commerce"], ["a10", "a13"], {"answerable"}),
    (["Not found:", "CEO"], ["a02"], {"partial", "none"}),
]


@pytest.fixture(scope="module")
def results(profile, alerts):
    a = Assistant(Settings(), TemplateClient(), profile, alerts, trace_dir=None)
    return demo.run_demo(a, transcript=None, verbose=False)


@pytest.mark.parametrize("i", range(6))
def test_demo_question(results, i):
    q, ans = results[i]
    must, cites, statuses = EXPECTED[i]
    for s in must:
        assert s in ans.text, f"Q{i + 1} missing {s!r}:\n{ans.text}"
    for c in cites:
        assert c in ans.citations, f"Q{i + 1} missing citation {c}"
    assert ans.gate_status in statuses
    assert ans.text.startswith("(rule-based answer)") or ans.method == "abstain"
    assert ans.errors == [], ans.errors  # template answers pass the validator


def test_no_tariff_claim_via_client(results):
    _, ans = results[1]
    assert "exposed to tariffs" not in ans.text
    assert "[PROFILE" not in ans.text
