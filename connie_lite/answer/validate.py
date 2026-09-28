"""Deterministic answer validator: citations, per-sentence coverage, and no entities outside the evidence."""
from __future__ import annotations

import re

from ..graph.store import NetworkxStore
from ..retrieval.linker import link
from ..retrieval.templates import is_focal_relationship
from ..schema import Evidence

CITATION_RE = re.compile(r"\[([A-Za-z0-9_, ]+)\]")
NOT_FOUND = "Not found:"
RULE_LABEL = "(rule-based answer)"
CHECKED_TYPES = ("Company", "Person", "Regulator")
_SENTENCE_END = re.compile(r"(?<=[.?!])\s+(?=\S)")
DISCOVERED_PHRASE = "newly discovered"
NOT_NAMED_RE = re.compile(r"\b(does not|doesn't|do not|don't|never)\s+(itself\s+|themselves\s+|explicitly\s+|directly\s+)?(name|mention)", re.I)
_BRACKETS = re.compile(r"\[[^\]]*\]")


def citations(text: str) -> list[str]:
    out: list[str] = []
    for group in CITATION_RE.findall(text):
        for cid in (c.strip() for c in group.split(",")):
            if cid and cid not in out:
                out.append(cid)
    return out


def split_sentences(text: str) -> list[str]:
    """Split on line breaks and ./?/! boundaries. Citation brackets are masked so '.' inside them never splits."""
    sentences: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-*• ").strip()
        if not line or line == RULE_LABEL:
            continue
        if line.startswith(RULE_LABEL):
            line = line[len(RULE_LABEL):].strip()
        masked = _BRACKETS.sub(lambda m: "x" * len(m.group()), line)
        start = 0
        for m in _SENTENCE_END.finditer(masked):
            sentences.append(line[start:m.start()].strip())
            start = m.end()
        sentences.append(line[start:].strip())
    return [s for s in sentences if s]


def validate(answer_text: str, evidence: Evidence, store: NetworkxStore, aliases: dict[str, str]) -> list[str]:
    errors: list[str] = []
    # 1. every cited id must be an allowed source
    for cid in citations(answer_text):
        if cid not in evidence.allowed_sources:
            errors.append(f"unknown citation [{cid}] (allowed: {', '.join(sorted(evidence.allowed_sources)) or 'none'})")
    # 2. every sentence cites, unless it is an explicit Not found: statement
    for sent in split_sentences(answer_text):
        if not sent.startswith(NOT_FOUND) and not CITATION_RE.search(sent):
            errors.append(f"sentence without citation: {sent!r}")
    # 3. every named company / person / regulator must be inside the retrieved subgraph
    named = set()
    for hit in link(answer_text, store, aliases).hits:
        named.add(hit.node_id)
        if store.type(hit.node_id) in CHECKED_TYPES and hit.node_id not in evidence.subgraph_nodes:
            errors.append(f"entity outside evidence: {store.name(hit.node_id)!r} (from {hit.surface!r})")
    # 4. honesty labels for the client relationships the answer names
    errors += missing_labels(answer_text, evidence, store, named)
    return errors


def missing_labels(answer_text: str, evidence: Evidence, store: NetworkxStore, named: set[str]) -> list[str]:
    rels = [e for p in evidence.paths for e in p.edges if is_focal_relationship(e) and e.dst in named]
    errors = []
    discovered = sorted({store.name(e.dst) for e in rels if e.status == "discovered"})
    if discovered and DISCOVERED_PHRASE not in answer_text.casefold():
        errors.append(f"must say 'newly discovered, not in the client profile' for: {', '.join(discovered)}")
    annotated = sorted({store.name(e.dst) for e in rels if e.annotation_only})
    if annotated and not NOT_NAMED_RE.search(answer_text):
        errors.append(f"must say the alert text itself does not name the client, for: {', '.join(annotated)}")
    return errors
