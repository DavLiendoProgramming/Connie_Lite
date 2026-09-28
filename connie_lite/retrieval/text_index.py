"""Text retrieval: BM25 over every alert (subject + body), including the noise alerts.

Used to rank "closest related evidence", to decide the gate's "none" (nothing in the corpus at all),
and as the BM25-only baseline in the eval. It never adds facts to an answer on its own.
"""
from __future__ import annotations

import bm25s

from ..schema import Alert

BM25_TOP = 6
# Minimum BM25 score for "the corpus has something on this". Empirical: off-topic questions score 0.0,
# questions that only share the client's name score < 1.0, a single distinctive term match scores > 1.2.
BM25_MIN = 1.0


class AlertIndex:
    """BM25 over all alerts (subject + body), including the noise alerts."""

    def __init__(self, alerts: list[Alert]) -> None:
        self.ids = [a.id for a in alerts]
        tokens = bm25s.tokenize([a.text for a in alerts], stopwords="en", show_progress=False)
        self.retriever = bm25s.BM25()
        self.retriever.index(tokens, show_progress=False)

    def scores(self, query: str) -> dict[str, float]:
        q = bm25s.tokenize([query], stopwords="en", return_ids=False, show_progress=False)[0]
        if not q:
            return {i: 0.0 for i in self.ids}
        return {i: float(s) for i, s in zip(self.ids, self.retriever.get_scores(q))}

    def top(self, query: str, k: int = BM25_TOP) -> list[tuple[str, float]]:
        ranked = sorted(self.scores(query).items(), key=lambda kv: (-kv[1], kv[0]))
        return [(i, s) for i, s in ranked[:k] if s > 0]
