"""Conversation state carried between turns (used for pronoun resolution in the planner)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .graph.ingest import FOCAL_ID

HISTORY_TURNS = 3


@dataclass
class ConversationState:
    last_focus: list[str] = field(default_factory=list)
    last_intent: str | None = None
    history: list[dict] = field(default_factory=list)   # last N {"question", "answer"}; planner input only

    def update(self, question: str, answer_text: str, intent: str, entity_ids: list[str], paths, store) -> None:
        self.last_focus = focus_from(paths, entity_ids, store)
        self.last_intent = intent
        self.history = (self.history + [{"question": question, "answer": answer_text}])[-HISTORY_TURNS:]

    def reset(self) -> None:
        self.last_focus, self.last_intent, self.history = [], None, []


def focus_from(paths, entity_ids: list[str], store) -> list[str]:
    """Non-focal companies on the kept paths; else any non-focal path node; else the plan's entities."""
    nodes: list[str] = []
    for p in paths:
        for n in p.nodes:
            if n != FOCAL_ID and n not in nodes:
                nodes.append(n)
    companies = [n for n in nodes if store.type(n) == "Company"]
    return companies or nodes or list(entity_ids)
