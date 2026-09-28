"""Deterministic entity linker: exact n-gram gazetteer match, then guarded fuzzy match, plus anaphora detection."""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from ..graph.store import ALERT_TYPE, NetworkxStore

MAX_NGRAM = 6
MAX_FUZZY_NGRAM = 4
FUZZY_MIN = 90
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*(?:['’]s\b|['’](?=\s|$))?")
ANAPHOR_RE = re.compile(
    r"\b(they|them|their|it|its|that (supplier|customer|competitor|company)|those|these)\b", re.IGNORECASE
)
# Never fuzzy-match an n-gram made only of these words.
FUZZY_STOPWORDS = frozenset(
    "a an and any are as at be by do does for from has have how in is it its of on or the their them they this "
    "to what which who with".split()
)


@dataclass(frozen=True)
class LinkHit:
    node_id: str
    surface: str
    score: float
    method: str       # "exact" | "fuzzy"
    start: int        # char offsets in the input text
    end: int


@dataclass(frozen=True)
class LinkResult:
    hits: tuple[LinkHit, ...]
    has_anaphor: bool

    @property
    def node_ids(self) -> list[str]:
        out: list[str] = []
        for h in self.hits:
            if h.node_id not in out:
                out.append(h.node_id)
        return out


def normalize_token(tok: str) -> str:
    tok = tok.casefold().replace("’", "'")
    if tok.endswith("'s"):
        tok = tok[:-2]
    return tok.rstrip("'")


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """(normalized token, start, end) for each word; possessive 's is stripped."""
    return [(normalize_token(m.group()), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def build_gazetteer(store: NetworkxStore, aliases: dict[str, str]) -> dict[str, str]:
    """normalized phrase -> node id, from every node name plus the alias table."""
    by_name: dict[str, str] = {}
    for nid in store.nodes():
        if store.type(nid) == ALERT_TYPE:
            continue
        by_name.setdefault(store.name(nid).casefold(), nid)
    gaz: dict[str, str] = {}
    for name, nid in sorted(by_name.items()):
        gaz[" ".join(t for t, _, _ in tokenize(name))] = nid
    for alias, canonical_name in sorted(aliases.items()):
        nid = by_name.get(canonical_name.casefold())
        if nid:
            gaz.setdefault(" ".join(t for t, _, _ in tokenize(alias)), nid)
    return gaz


def link(text: str, store: NetworkxStore, aliases: dict[str, str]) -> LinkResult:
    gaz = build_gazetteer(store, aliases)
    toks = tokenize(text)
    used = [False] * len(toks)
    hits: list[LinkHit] = []

    def take(i: int, n: int, nid: str, score: float, method: str) -> None:
        for k in range(i, i + n):
            used[k] = True
        start, end = toks[i][1], toks[i + n - 1][2]
        hits.append(LinkHit(nid, text[start:end], float(score), method, start, end))

    # 1) exact, longest first, no overlaps
    for n in range(min(MAX_NGRAM, len(toks)), 0, -1):
        for i in range(len(toks) - n + 1):
            if any(used[i:i + n]):
                continue
            phrase = " ".join(t for t, _, _ in toks[i:i + n])
            if phrase in gaz:
                take(i, n, gaz[phrase], 100, "exact")

    # 2) fuzzy on the remaining spans
    keys = sorted(gaz)
    for n in range(min(MAX_FUZZY_NGRAM, len(toks)), 0, -1):
        for i in range(len(toks) - n + 1):
            if any(used[i:i + n]):
                continue
            words = [t for t, _, _ in toks[i:i + n]]
            if all(w in FUZZY_STOPWORDS for w in words) or len(" ".join(words)) < 4:
                continue
            phrase = " ".join(words)
            best = process.extractOne(phrase, keys, scorer=fuzz.token_set_ratio, score_cutoff=FUZZY_MIN)
            if best is None:
                continue
            key, score, _ = best
            surface = text[toks[i][1]:toks[i + n - 1][2]]
            # token_set_ratio scores a subset as 100 ("automation" vs "warehouse automation").
            # Accept a subset match only as proper-noun shorthand: capitalised surface that starts like
            # the name ("Ferrotech" -> "Ferrotech Alloys"). Otherwise require a near-exact whole-string
            # match (typos, plural/singular).
            if fuzz.ratio(phrase, key) < FUZZY_MIN and not (surface[:1].isupper() and key.split()[0] == words[0]):
                continue
            take(i, n, gaz[key], score, "fuzzy")

    hits.sort(key=lambda h: (h.start, h.node_id))
    return LinkResult(hits=tuple(hits), has_anaphor=ANAPHOR_RE.search(text) is not None)


def anaphor_spans(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in ANAPHOR_RE.finditer(text)]
