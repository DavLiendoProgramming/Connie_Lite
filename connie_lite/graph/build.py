"""Build the graph: entity + alert nodes, MENTIONS edges (evidence layer), then EDGE_RULES in order."""
from __future__ import annotations

import logging
from collections import Counter

from ..schema import Alert, Support
from .ingest import focal_id, load_corpus
from .rules import EDGE_RULES, RuleFn
from .store import ALERT_TYPE, MENTIONS, NetworkxStore

log = logging.getLogger(__name__)


def build_graph(profile: dict, alerts: list[Alert], rules: list[tuple[str, str, RuleFn]] | None = None) -> NetworkxStore:
    store = NetworkxStore()
    focal = focal_id(profile)
    store.add_node(focal, "Company", profile["client_name"], focal=True)
    graph_alerts = [a for a in sorted(alerts, key=lambda a: a.id) if a.entities]  # skip noise alerts

    for alert in graph_alerts:
        store.add_node(f"alert:{alert.id}", ALERT_TYPE, alert.subject, date=alert.date.isoformat())
        for e in alert.entities:
            attrs = {k: v for k, v in e.attrs.items() if k != "related_to_focal"}
            store.add_node(e.node_id, e.node_type, e.name, **attrs)
            store.add_support(f"alert:{alert.id}", MENTIONS, e.node_id, Support("text", alert.id, alert.date))

    for _, scope, fn in rules or EDGE_RULES:
        if scope == "once":
            fn(store, profile, None)
        else:
            for alert in graph_alerts:
                fn(store, profile, alert)

    log.info(summary(store))
    return store


def summary(store: NetworkxStore) -> str:
    node_counts = Counter(store.type(n) for n in store.nodes())
    edges = store.edges()
    rel_counts = Counter(e.rel for e in edges)
    discovered = [e for e in edges if e.rel != MENTIONS and e.status == "discovered"]
    focal_discovered = [e for e in discovered if store.node(e.src).get("focal")]
    lines = ["nodes: " + ", ".join(f"{t}={c}" for t, c in sorted(node_counts.items()))]
    lines.append("edges: " + ", ".join(f"{r}={c}" for r, c in sorted(rel_counts.items())))
    lines.append(f"discovered (non-profile) semantic edges: {len(discovered)}")
    lines.append("discovered focal edges: " + "; ".join(f"{e.rel}->{store.name(e.dst)} {list(e.sources)}" for e in focal_discovered))
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(build_graph(*load_corpus())))
