"""Answer generation flow: gate "none" -> abstain (no LLM); template provider -> rule-based renderer;
LLM -> answer from the EVIDENCE block only, validate, one retry with the errors, else fall back to the renderer."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..graph.store import NetworkxStore
from ..retrieval.gate import GateResult
from ..retrieval.templates import is_focal_relationship
from ..schema import PROFILE_SOURCE, EdgeView, Evidence, Path
from .render import render_template
from .validate import citations, validate


@dataclass
class Answer:
    text: str
    citations: list[str]
    gate_status: str
    fallback: bool = False
    paths: list[Path] = field(default_factory=list)
    trace_id: str | None = None
    method: str = "template"            # "template" | "llm" | "abstain"
    errors: list[str] = field(default_factory=list)


# ---- LLM prompt ---------------------------------------------------------------------
ANSWER_SYSTEM = """You answer an advisor's question about a client using ONLY the EVIDENCE block.
Rules:
- Do not use outside knowledge.
- Every sentence must end with one or more citations in square brackets, using only the listed source ids, e.g. [a09] or [PROFILE] or [a09, PROFILE].
- A sentence stating that something is not in the evidence must start with "Not found:" and needs no citation.
- Every sentence needs a citation, including any opening summary sentence (never start with an uncited "Yes.").
- When you mention an entity whose edge is marked status=discovered, you MUST say it is "newly discovered, not in the client profile".
- When you mention an entity whose edge is marked alert_text_names_client=no, you MUST say the alert text itself does not name the client (one sentence may cover several such entities).
- If GATE is partial, explicitly state each missing part in a sentence starting with "Not found:".
- Never name a company, person or regulator that does not appear in the EVIDENCE block.
- Be concise: 2-6 sentences, plain prose, no headings or bullet lists."""


def format_edge(e: EdgeView, store: NetworkxStore, evidence: Evidence) -> str:
    sup = ", ".join(s.label() for s in e.supports if s.source in evidence.allowed_sources)
    line = f"{store.name(e.src)} -{e.rel}-> {store.name(e.dst)} [{sup}]"
    if e.attrs.get("role"):
        line += f" role={e.attrs['role']}"
    if is_focal_relationship(e):
        line += f" status={e.status}"
        if e.annotation_only:
            line += " alert_text_names_client=no"
    return line


def evidence_block(evidence: Evidence, store: NetworkxStore) -> str:
    out = ["PATHS:"]
    for i, p in enumerate(evidence.paths, 1):
        for j, e in enumerate(p.edges):
            out.append(f"{f'{i}.':<3} {format_edge(e, store, evidence)}" if j == 0 else f"    {format_edge(e, store, evidence)}")
    if not evidence.paths:
        out.append("(none)")
    out.append("ALERTS:")
    for aid in sorted(evidence.alerts):
        a = evidence.alerts[aid]
        out.append(f"[{aid}] {a.date.isoformat()} {a.subject}\n{a.body}")
    if evidence.profile_facts:
        out.append("PROFILE:")
        out += [f"[{PROFILE_SOURCE}] {f}" for f in evidence.profile_facts]
    return "\n".join(out)


def answer_user_message(plan, evidence: Evidence, gate_result: GateResult, store: NetworkxStore) -> str:
    return "\n".join([
        f"QUESTION: {plan.resolved_question}",
        f"GATE: {gate_result.status}" + (f"; missing: {', '.join(gate_result.missing)}" if gate_result.missing else ""),
        f"ALLOWED SOURCE IDS: {', '.join(sorted(evidence.allowed_sources))}",
        "EVIDENCE:",
        evidence_block(evidence, store),
    ])


# ---- flow -----------------------------------------------------------------------------
def generate(plan, evidence: Evidence, gate_result: GateResult, llm, store: NetworkxStore, aliases: dict[str, str],
             log: dict | None = None) -> Answer:
    """`log` (optional) receives prompt messages, raw outputs and validator errors for the trace."""
    log = log if log is not None else {}

    def done(text: str, method: str, fallback: bool = False, errors: list[str] | None = None) -> Answer:
        return Answer(text, citations(text), gate_result.status, fallback, list(evidence.paths), None, method, errors or [])

    if gate_result.status == "none":  # no LLM call
        return done(render_template(plan, evidence, gate_result, store), "abstain")
    if getattr(llm, "name", "template") == "template":
        text = render_template(plan, evidence, gate_result, store)
        return done(text, "template", errors=validate(text, evidence, store, aliases))

    messages = [{"role": "user", "content": answer_user_message(plan, evidence, gate_result, store)}]
    log["messages"], log["raw_outputs"], log["validator_errors"] = messages, [], []
    text = llm.complete_text(ANSWER_SYSTEM, messages)
    log["raw_outputs"].append(text)
    errors = validate(text, evidence, store, aliases)
    log["validator_errors"].append(errors)
    if errors:
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "Your answer failed validation:\n- " + "\n- ".join(errors) + "\nRewrite it following every rule."},
        ]
        log["messages"] = messages
        text = llm.complete_text(ANSWER_SYSTEM, messages)
        log["raw_outputs"].append(text)
        errors = validate(text, evidence, store, aliases)
        log["validator_errors"].append(errors)
    if errors:
        fallback_text = render_template(plan, evidence, gate_result, store)
        return done(fallback_text, "template", fallback=True, errors=errors)
    return done(text, "llm")
