"""Question -> validated QueryPlan.

Template provider: keyword rules (rule_plan). LLM providers: structured output constrained to a
dynamically built schema whose entity ids are limited to a small candidate list. Either way the
plan is post-validated by code.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, create_model

from ..config import clamp_hops
from ..graph.ingest import FOCAL_ID
from ..graph.store import NetworkxStore
from ..state import ConversationState
from .evidence import FINDERS
from .linker import LinkResult, anaphor_spans, link, tokenize
from .traversals import REL_KEYWORDS, resolve_term

INTENTS = tuple(FINDERS)   # generic traversals + every registered template
TARGET_TYPES = ("Commodity", "Theme", "Regulator", "Country", "Market", "Person")
EXPOSURE_TARGET_TYPES = ("Theme", "Commodity", "Regulator")
ROLE_WORDS = ("ceo", "cfo", "cto", "coo", "president")
CLIENT_PHRASES = ("my client", "the client", "our client")
# Filler words ignored when looking for an unlinked term the question asks about.
FILLER = frozenset("""a about an and any are as at be by can could did do does for from has have how in is it its
    know make makes me my of on or our tell that the their them they this to us was we what when where which who
    why will with you operate operates operating""".split())


class _PlanBase(BaseModel):
    model_config = {"extra": "forbid"}


def make_plan_model(candidate_ids: list[str]) -> type[BaseModel]:
    ids = tuple(sorted(set(candidate_ids))) or (FOCAL_ID,)
    return create_model(
        "QueryPlan",
        __base__=_PlanBase,
        intent=(Literal[INTENTS], ...),
        entity_ids=(list[Literal[ids]], ...),
        target_type=(Literal[TARGET_TYPES] | None, ...),
        target_term=(str | None, ...),
        max_hops=(int, ...),
        resolved_question=(str, ...),
    )


@dataclass
class PlanResult:
    plan: BaseModel
    link: LinkResult
    candidates: list[str]
    method: str                    # "rule" | "llm"
    raw: dict                      # plan before post-validation


# ---- rule-based planner (template provider) -------------------------------------
def _has(q: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", q) for w in words)


def _first_of_type(store: NetworkxStore, hits: list[str], *types: str) -> str | None:
    return next((h for h in hits if store.type(h) in types), None)


def unlinked_term(question: str, link_result: LinkResult) -> str | None:
    """What a one-entity question asks about, beyond the entity: a relation word ("suppliers"),
    or the remaining unlinked words ("market share Japan")."""
    covered = [(h.start, h.end) for h in link_result.hits]
    words = [(tok, question[s:e]) for tok, s, e in tokenize(question)
             if tok not in FILLER and not any(cs <= s < ce for cs, ce in covered)]
    if words and all(tok in REL_KEYWORDS for tok, _ in words):
        return words[0][0]
    return " ".join(surface for _, surface in words) or None


def _resolve_pronouns(question: str, names: list[str]) -> str:
    joined = " and ".join(names)
    out = question
    for start, end, word in reversed(anaphor_spans(question)):
        possessive = word.lower() in ("their", "its")
        owner = (f"{joined}'" if joined.endswith("s") else f"{joined}'s") if possessive else joined
        out = out[:start] + owner + out[end:]
    return out


def rule_plan(question: str, link_result: LinkResult, state: ConversationState, store: NetworkxStore, max_hops: int) -> dict:
    """Ordered keyword rules; first match wins. The LLM planner replaces this when a provider is configured."""
    q = question.casefold()
    hits = link_result.node_ids
    plan = {"intent": None, "target_type": None, "target_term": None, "max_hops": max_hops}
    target = None

    # named templates
    if _has(q, "supplier", "suppliers") and _has(q, "commodity", "commodities", "input", "material", "materials"):
        target = _first_of_type(store, hits, "Commodity")
        plan |= {"intent": "SUPPLIER_RISK", "target_type": "Commodity"}
    elif _has(q, "competitor", "competitors") and _has(q, "customer", "customers") and _has(q, "market", "markets"):
        target = _first_of_type(store, hits, "Market")
        plan |= {"intent": "SHARED_MARKET"}
    elif "export control" in q or "regulat" in q or "supply chain" in q:
        target = _first_of_type(store, hits, "Regulator")
        plan |= {"intent": "SUPPLIER_RISK", "target_type": "Regulator", "max_hops": max(3, max_hops)}
    elif (_has(q, "new", "discovered", "unknown") or re.search(r"(\bnot\b|n't\b).*\bprofile\b", q)) and _has(
            q, "supplier", "suppliers", "customer", "customers", "relationship", "relationships"):
        plan |= {"intent": "DISCOVERED"}
    # generic traversals
    elif _has(q, "exposure", "exposed", "risk") and (target := _first_of_type(store, hits, *EXPOSURE_TARGET_TYPES)):
        plan |= {"intent": "CONNECT", "target_type": store.type(target)}
    elif role := next((r for r in ROLE_WORDS if _has(q, r)), None):
        plan |= {"intent": "NEIGHBORHOOD", "target_type": "Person", "target_term": role.upper()}
    if target:
        plan["target_term"] = store.name(target)

    # entities: linked (minus the target) -> pronoun + last focus -> "my client"
    entity_ids = [h for h in hits if h != target]
    resolved = question
    if not entity_ids and link_result.has_anaphor and state.last_focus:
        entity_ids = list(state.last_focus)
        resolved = _resolve_pronouns(question, [store.name(n) for n in entity_ids])
    if not entity_ids and any(p in q for p in CLIENT_PHRASES):
        entity_ids = [FOCAL_ID]

    if plan["intent"] is None:  # default: connect several entities, or walk around one
        if len(entity_ids) >= 2:
            plan["intent"] = "CONNECT"
        else:
            plan |= {"intent": "NEIGHBORHOOD", "target_term": unlinked_term(question, link_result) if entity_ids else None}

    return plan | {"entity_ids": entity_ids, "resolved_question": resolved}


# ---- LLM planner -------------------------------------------------------------
PLANNER_SYSTEM = """You turn an advisor's question about a client into a graph retrieval plan (JSON).
Intents (generic traversals first, then named multi-hop templates):
- NEIGHBORHOOD: facts around one entity (walk 1-2 hops). For executives set target_type "Person" and target_term to the role. e.g. "Tell me about Kestrel", "Who is Solstice's CFO?"
- CONNECT: how an entity connects to a target (theme, commodity, regulator, country, market) in target_term, or how two entities connect. e.g. "What is Kestrel's exposure to tariffs?"
- SUPPLIER_RISK: risk reaching the client through its suppliers. target_type "Commodity" for commodity risk (2 hops); "Regulator" for regulatory / export-control risk via supplier countries (max_hops 3). e.g. "Which suppliers carry commodity risk?", "Could new export controls hit our supply chain?"
- SHARED_MARKET: competitors operating in the same end markets as the client's customers. e.g. "Are competitors moving into our customers' markets?"
- DISCOVERED: client relationships not in the client profile. e.g. "Any new customers we didn't know about?"
Rules:
- Choose entity_ids ONLY from the provided candidates. Never invent ids.
- Resolve pronouns (they/their/it/its/those) using the conversation context and last_focus, and write resolved_question with names substituted.
- target_term is the SPECIFIC thing asked about (e.g. "tariffs", "rare earth magnets", "CEO"), or null when the question asks "which one" (e.g. "which commodity" -> null).
- max_hops: 2 unless the question needs a longer chain (supplier -> country -> regulator needs 3)."""


def _node_brief(store: NetworkxStore, nid: str) -> dict:
    return {"id": nid, "name": store.name(nid), "type": store.type(nid)}


def llm_plan(question: str, state: ConversationState, llm, store: NetworkxStore, link_result: LinkResult,
             candidates: list[str], max_hops: int) -> dict:
    model = make_plan_model(candidates)
    payload = {
        "question": question,
        "recent_turns": state.history,
        "last_focus": [_node_brief(store, n) for n in state.last_focus],
        "candidates": [_node_brief(store, n) for n in candidates],
        "linked_mentions": [{"surface": h.surface, "id": h.node_id} for h in link_result.hits],
        "question_has_pronoun": link_result.has_anaphor,
        "default_max_hops": max_hops,
    }
    return llm.complete_json(PLANNER_SYSTEM, json.dumps(payload, indent=1), model).model_dump()


GENERIC_TERM_WORDS = frozenset(REL_KEYWORDS) | {"risk", "risks", "exposure", "exposures", "relationship", "relationships",
                                                 "theme", "themes", "regulatory", "new", "discovered", "any"}


def is_generic_term(term: str | None) -> bool:
    return bool(term) and all(tok in GENERIC_TERM_WORDS for tok, _, _ in tokenize(term))


def post_validate(raw: dict, store: NetworkxStore, link_result: LinkResult, candidates: list[str],
                  aliases: dict[str, str]) -> BaseModel:
    data = dict(raw)
    data["entity_ids"] = [e for e in dict.fromkeys(data.get("entity_ids") or []) if store.has_node(e)]
    target = resolve_term(data.get("target_term"), store, aliases)
    if target in data["entity_ids"] and len(data["entity_ids"]) > 1:
        data["entity_ids"].remove(target)  # the thing asked about is not also a subject
    if is_generic_term(data.get("target_term")):
        data["target_term"] = None  # "commodity risk" names a category, not a specific target to filter on
    data["max_hops"] = clamp_hops(data.get("max_hops") or 2)
    if data.get("target_type") not in TARGET_TYPES:
        data["target_type"] = None
    term = (data.get("target_term") or "").casefold()
    if data.get("intent") == "NEIGHBORHOOD" and target and data.get("target_type") != "Person" and term not in REL_KEYWORDS:
        data["intent"] = "CONNECT"  # a resolvable target means "how does X connect to T"
    # candidates must cover the chosen ids so the dynamic model validates
    return make_plan_model(sorted(set(candidates) | set(data["entity_ids"]))).model_validate(data)


def plan(question: str, state: ConversationState, llm, store: NetworkxStore, aliases: dict[str, str],
         max_hops: int = 2) -> PlanResult:
    link_result = link(question, store, aliases)
    candidates = list(dict.fromkeys([*link_result.node_ids, *state.last_focus, FOCAL_ID]))
    if getattr(llm, "name", "template") == "template":
        raw, method = rule_plan(question, link_result, state, store, max_hops), "rule"
    else:
        raw, method = llm_plan(question, state, llm, store, link_result, candidates, max_hops), "llm"
    return PlanResult(post_validate(raw, store, link_result, candidates, aliases), link_result, candidates, method, raw)
