"""Scripted multi-turn demo (state carries over). Writes demo_transcript.md.

    python scripts/demo.py                  # template provider, no keys
    LLM_PROVIDER=anthropic LLM_MODEL=... python scripts/demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connie_lite.assistant import Assistant  # noqa: E402
from connie_lite.cli import fmt_edge  # noqa: E402

DEMO_QUESTIONS = [
    "Which of Solstice's suppliers carry commodity risk, and which commodity?",
    "And what about their exposure to tariffs?",
    "Are any of Solstice's competitors pushing into the same end markets as its customers?",
    "Does Solstice have any supplier or customer relationships that aren't in its profile?",
    "Could new export controls hit Solstice's supply chain?",
    "Who is Solstice's CEO?",
]


def run_demo(assistant: Assistant | None = None, transcript: Path | None = ROOT / "demo_transcript.md",
             verbose: bool = True) -> list[tuple[str, object]]:
    a = assistant or Assistant(trace_dir=ROOT / "traces")
    results = []
    md = ["# Connie-Lite demo transcript", "",
          f"Provider: `{a.llm.name}`" + (" (rule-based answers, no LLM)" if a.llm.name == "template" else f", model `{a.llm.model}`"),
          ""]
    for i, q in enumerate(DEMO_QUESTIONS, 1):
        ans = a.ask(q)
        results.append((q, ans))
        plan = a.last_plan
        if verbose:
            print(f"\nQ{i}: {q}\n{ans.text}\n  -- gate={ans.gate_status} method={ans.method} citations={ans.citations}")
        md += [f"## Q{i}. {q}", "",
               f"*Plan:* intent `{plan.intent}`, entities `{plan.entity_ids}`, target `{plan.target_term}`, "
               f"max_hops {plan.max_hops}. Resolved question: \"{plan.resolved_question}\"", "",
               "```text", ans.text, "```", "",
               f"*Gate:* `{ans.gate_status}` · *method:* `{ans.method}` · *citations:* {', '.join(ans.citations) or 'none'}", ""]
        if ans.paths:
            md.append("<details><summary>Graph paths used</summary>\n")
            for j, p in enumerate(ans.paths, 1):
                md.append(f"{j}. score {p.score:.3f}")
                md += [f"   - `{fmt_edge(a, e)}`" for e in p.edges]
            md += ["", "</details>", ""]
    if transcript:
        transcript.write_text("\n".join(md))
        if verbose:
            print(f"\ntranscript written to {transcript}")
    return results


if __name__ == "__main__":
    run_demo()
