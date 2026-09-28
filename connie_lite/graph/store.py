"""Graph storage behind a small protocol; networkx implementation.

Two layers share one MultiDiGraph:
- semantic layer: entity nodes and typed relations (used for traversal)
- evidence layer: `alert:<id>` nodes and MENTIONS edges (ignored by traversal)
"""
from __future__ import annotations

from itertools import product
from typing import Protocol

import networkx as nx

from ..schema import EdgeView, Support

MENTIONS = "MENTIONS"
ALERT_TYPE = "Alert"


class GraphStore(Protocol):
    def add_node(self, node_id: str, node_type: str, name: str, **attrs) -> None: ...
    def add_support(self, src: str, rel: str, dst: str, support: Support, **attrs) -> None: ...
    def has_node(self, node_id: str) -> bool: ...
    def node(self, node_id: str) -> dict: ...
    def nodes(self, node_type: str | None = None) -> list[str]: ...
    def edges(self, rel: str | None = None) -> list[EdgeView]: ...
    def edges_from(self, node_id: str, rel: str | None = None) -> list[EdgeView]: ...
    def edges_to(self, node_id: str, rel: str | None = None) -> list[EdgeView]: ...
    def edge(self, src: str, rel: str, dst: str) -> EdgeView | None: ...
    def simple_paths(self, src: str, dst: str, max_hops: int, exclude: set[str]) -> list[list[EdgeView]]: ...
    def walk(self, start: str, max_hops: int, exclude: set[str]) -> list[list[EdgeView]]: ...


def _edge_sort_key(e: EdgeView) -> tuple:
    return (e.src, e.rel, e.dst)


class NetworkxStore:
    def __init__(self) -> None:
        self.G = nx.MultiDiGraph()

    # ---- writes -------------------------------------------------------
    def add_node(self, node_id: str, node_type: str, name: str, **attrs) -> None:
        if node_id in self.G:
            self.G.nodes[node_id].update({k: v for k, v in attrs.items() if v is not None})
            return
        self.G.add_node(node_id, type=node_type, name=name, **attrs)

    def add_support(self, src: str, rel: str, dst: str, support: Support, **attrs) -> None:
        for n in (src, dst):
            if n not in self.G:
                raise KeyError(f"add_support: unknown node {n!r}")
        if not self.G.has_edge(src, dst, key=rel):
            self.G.add_edge(src, dst, key=rel, supports=[], attrs={})
        data = self.G.edges[src, dst, rel]
        if support not in data["supports"]:
            data["supports"].append(support)
        data["attrs"].update(attrs)

    # ---- reads --------------------------------------------------------
    def has_node(self, node_id: str) -> bool:
        return node_id in self.G

    def node(self, node_id: str) -> dict:
        return dict(self.G.nodes[node_id])

    def name(self, node_id: str) -> str:
        return self.G.nodes[node_id]["name"]

    def type(self, node_id: str) -> str:
        return self.G.nodes[node_id]["type"]

    def nodes(self, node_type: str | None = None) -> list[str]:
        return sorted(n for n, d in self.G.nodes(data=True) if node_type is None or d["type"] == node_type)

    def _view(self, src: str, dst: str, rel: str) -> EdgeView:
        data = self.G.edges[src, dst, rel]
        supports = tuple(sorted(data["supports"], key=lambda s: s.sort_key))
        return EdgeView(src=src, rel=rel, dst=dst, supports=supports, attrs=dict(data["attrs"]))

    def edges(self, rel: str | None = None) -> list[EdgeView]:
        out = [self._view(u, v, k) for u, v, k in self.G.edges(keys=True) if rel is None or k == rel]
        return sorted(out, key=_edge_sort_key)

    def edges_from(self, node_id: str, rel: str | None = None) -> list[EdgeView]:
        out = [self._view(node_id, v, k) for _, v, k in self.G.out_edges(node_id, keys=True) if rel is None or k == rel]
        return sorted(out, key=_edge_sort_key)

    def edges_to(self, node_id: str, rel: str | None = None) -> list[EdgeView]:
        out = [self._view(u, node_id, k) for u, _, k in self.G.in_edges(node_id, keys=True) if rel is None or k == rel]
        return sorted(out, key=_edge_sort_key)

    def edge(self, src: str, rel: str, dst: str) -> EdgeView | None:
        return self._view(src, dst, rel) if self.G.has_edge(src, dst, key=rel) else None

    # ---- semantic traversal (ignores alert nodes and MENTIONS) ---------
    def semantic_edges(self, node_id: str) -> list[EdgeView]:
        """All non-MENTIONS edges touching node_id, either direction."""
        out = [e for e in self.edges_from(node_id) + self.edges_to(node_id) if e.rel != MENTIONS]
        return sorted(out, key=_edge_sort_key)

    def _semantic_undirected(self, exclude: set[str]):
        G = self.G
        view = nx.subgraph_view(
            G,
            filter_node=lambda n: n not in exclude and G.nodes[n]["type"] != ALERT_TYPE,
            filter_edge=lambda u, v, k: k != MENTIONS,
        )
        return view.to_undirected(as_view=True)

    def edges_between(self, a: str, b: str) -> list[EdgeView]:
        out = [self._view(a, b, k) for k in self.G.get_edge_data(a, b, default={}) if k != MENTIONS]
        out += [self._view(b, a, k) for k in self.G.get_edge_data(b, a, default={}) if k != MENTIONS]
        return sorted(out, key=_edge_sort_key)

    def simple_paths(self, src: str, dst: str, max_hops: int, exclude: set[str]) -> list[list[EdgeView]]:
        if src not in self.G or dst not in self.G or src == dst:
            return []
        U = self._semantic_undirected(set(exclude) - {src, dst})
        node_paths = sorted({tuple(p) for p in nx.all_simple_paths(U, src, dst, cutoff=max_hops)})
        out: list[list[EdgeView]] = []
        for np_ in node_paths:
            hops = [self.edges_between(a, b) for a, b in zip(np_, np_[1:])]
            out.extend(list(combo) for combo in product(*hops))  # parallel rels -> separate paths
        return sorted(out, key=lambda es: tuple(e.id for e in es))

    def walk(self, start: str, max_hops: int, exclude: set[str]) -> list[list[EdgeView]]:
        """All simple paths of 1..max_hops edges starting at `start`, either edge direction.
        Paths may end at an excluded node but never continue through one (the start is never excluded)."""
        exclude = set(exclude) - {start}
        out: list[list[EdgeView]] = []

        def dfs(node: str, path: list[EdgeView], visited: set[str]) -> None:
            for e in self.semantic_edges(node):
                nxt = e.other(node)
                if nxt in visited:
                    continue
                out.append(path + [e])
                if len(path) + 1 < max_hops and nxt not in exclude:
                    dfs(nxt, path + [e], visited | {nxt})

        if start in self.G:
            dfs(start, [], {start})
        return sorted(out, key=lambda es: tuple(e.id for e in es))
