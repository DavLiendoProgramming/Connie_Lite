"""Evaluation harness.

    python eval/run_eval.py              # template provider (default, no keys)
    LLM_PROVIDER=anthropic LLM_MODEL=claude-haiku-4-5 REPLAY_MODE=record python eval/run_eval.py

Metrics
  path recall              expected edges retrieved / expected edges (answerable items)
  answerable coverage      answerable items the gate did not abstain on
  citation coverage        sentences with a citation or "Not found:" / sentences
  citation validity        cited ids inside the allowed evidence set / cited ids
  invented-entity rate     answers naming a company/person/regulator outside the evidence subgraph / answers
  abstention accuracy      unanswerable items that end partial/none AND say "Not found:" / unanswerable items
  multi-hop recall@6       expected alert ids in the evidence: graph retrieval vs BM25-only top-6 baseline
  perturbation             rebuild graph without a09: demo Q1 must become partial/none
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connie_lite.answer.llm import make_client  # noqa: E402
from connie_lite.answer.validate import (  # noqa: E402
    CITATION_RE,
    NOT_FOUND,
    citations,
    split_sentences,
)
from connie_lite.assistant import Assistant  # noqa: E402
from connie_lite.config import load_settings  # noqa: E402
from connie_lite.graph.ingest import load_corpus  # noqa: E402
from connie_lite.retrieval.linker import link  # noqa: E402
from connie_lite.schema import PROFILE_SOURCE  # noqa: E402
from eval.golden import HAND_ITEMS, GoldenItem  # noqa: E402

K = 6


def ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def run_items(items: list[GoldenItem], make_assistant) -> list[dict]:
    """Run items; items sharing a `conversation` run in one session, others each in a fresh state."""
    rows = []
    a = make_assistant()
    current = None
    for item in items:
        if item.conversation is None or item.conversation != current:
            a.reset()
            current = item.conversation
        ans = a.ask(item.question)
        rows.append({"item": item, "answer": ans, "evidence": a.last_evidence, "plan": a.last_plan,
                     "bm25": [i for i, _ in a.index.top(item.question, K)], "assistant": a})
    return rows


def score(rows: list[dict]) -> dict:
    m: dict[str, list] = {k: [0, 0] for k in ("path", "coverage", "validity", "invented", "abstain", "answerable",
                                              "mh_graph", "mh_bm25", "contains")}
    failures = []
    for r in rows:
        item, ans, ev, a = r["item"], r["answer"], r["evidence"], r["assistant"]
        retrieved = {(e.src, e.rel, e.dst) for p in ev.paths for e in p.edges}
        if item.answerable:
            m["path"][0] += len(item.expected_edges & retrieved)
            m["path"][1] += len(item.expected_edges)
            m["answerable"][0] += ans.gate_status == "answerable"
            m["answerable"][1] += 1
            if item.expected_edges - retrieved:
                failures.append(f"{item.id}: missing edges {sorted(item.expected_edges - retrieved)}")
        else:
            ok = ans.gate_status in ("partial", "none") and NOT_FOUND in ans.text
            m["abstain"][0] += ok
            m["abstain"][1] += 1
            if not ok:
                failures.append(f"{item.id}: expected abstention, got {ans.gate_status}")
        sents = split_sentences(ans.text)
        m["coverage"][0] += sum(1 for s in sents if s.startswith(NOT_FOUND) or CITATION_RE.search(s))
        m["coverage"][1] += len(sents)
        cited = citations(ans.text)
        m["validity"][0] += sum(1 for c in cited if c in ev.allowed_sources)
        m["validity"][1] += len(cited)
        invented = [h for h in link(ans.text, a.store, a.aliases).hits
                    if a.store.type(h.node_id) in ("Company", "Person", "Regulator") and h.node_id not in ev.subgraph_nodes]
        m["invented"][0] += bool(invented)
        m["invented"][1] += 1
        missing_text = [s for s in item.must_contain if s not in ans.text]
        m["contains"][0] += not missing_text
        m["contains"][1] += 1
        if missing_text:
            failures.append(f"{item.id}: answer lacks {missing_text}")
        if item.multi_hop:
            expected = item.expected_sources - {PROFILE_SOURCE}
            m["mh_graph"][0] += len(expected & set(ev.alerts))
            m["mh_graph"][1] += len(expected)
            m["mh_bm25"][0] += len(expected & set(r["bm25"]))
            m["mh_bm25"][1] += len(expected)
    return {k: ratio(*v) for k, v in m.items()} | {"n": {k: v[1] for k, v in m.items()}, "failures": failures}


def perturbation(settings) -> tuple[bool, str]:
    profile, alerts = load_corpus(ROOT / "data")
    a = Assistant(settings, make_client(settings), profile, [x for x in alerts if x.id != "a09"], trace_dir=None)
    ans = a.ask(HAND_ITEMS[0].question)
    return ans.gate_status in ("partial", "none"), ans.gate_status


def main() -> None:
    settings = load_settings()
    client = make_client(settings)
    profile, alerts = load_corpus(ROOT / "data")
    rows = run_items(HAND_ITEMS, lambda: Assistant(settings, client, profile, alerts, trace_dir=None))
    result = score(rows)
    pert_ok, pert_status = perturbation(settings)

    print(f"provider={client.name} model={getattr(client, 'model', None)} replay={settings.replay_mode}  items={len(rows)}\n")
    for label, key in [
        ("path recall", "path"), ("answerable coverage", "answerable"), ("citation coverage", "coverage"),
        ("citation validity", "validity"), ("invented-entity rate", "invented"), ("abstention accuracy", "abstain"),
        ("expected text present", "contains"),
        ("multi-hop recall@6 (graph)", "mh_graph"), ("multi-hop recall@6 (BM25 only)", "mh_bm25"),
    ]:
        print(f"{label:<34}{fmt(result[key]):>8}")
    print(f"{'perturbation (drop a09 -> Q1)':<34}{'PASS' if pert_ok else 'FAIL'} ({pert_status})")
    print(f"\nfailures: {len(result['failures'])}")
    for f in result["failures"]:
        print("  -", f)


if __name__ == "__main__":
    main()
