"""Interactive REPL: `python -m connie_lite`."""
from __future__ import annotations

import sys

from .assistant import Assistant
from .graph.build import summary
from .retrieval.linker import link

HELP = """Ask a question, or use a command:
  :why            kept paths with supports      :graph <name>   1-hop neighborhood with supports
  :hops N         set max hops                  :reset          clear conversation state
  :quit"""


def fmt_edge(a: Assistant, e) -> str:
    sup = ", ".join(s.label() for s in e.supports)
    role = f" role={e.attrs['role']}" if e.attrs.get("role") else ""
    return f"{a.store.name(e.src)} -{e.rel}-> {a.store.name(e.dst)}{role}  [{sup}] ({e.status})"


def cmd_why(a: Assistant) -> str:
    if not a.last_answer:
        return "no answer yet"
    if not a.last_answer.paths:
        return "no graph paths were kept for the last answer"
    out = []
    for i, p in enumerate(a.last_answer.paths, 1):
        out.append(f"{i}. score={p.score:.3f}")
        out += [f"   {fmt_edge(a, e)}" for e in p.edges]
    return "\n".join(out)


def cmd_graph(a: Assistant, name: str) -> str:
    hits = link(name, a.store, a.aliases).hits
    if not hits:
        return f"no entity matches {name!r}"
    nid = hits[0].node_id
    edges = a.store.semantic_edges(nid)
    return "\n".join([f"{a.store.name(nid)} ({nid}), {len(edges)} edges:"] + [f"  {fmt_edge(a, e)}" for e in edges])


def handle(a: Assistant, line: str) -> str | None:
    """Return text to print, or None to quit."""
    cmd, _, arg = line.partition(" ")
    if cmd in (":quit", ":q", ":exit"):
        return None
    if cmd == ":help":
        return HELP
    if cmd == ":why":
        return cmd_why(a)
    if cmd == ":hops":
        try:
            return f"max hops = {a.set_hops(int(arg))}"
        except ValueError:
            return "usage: :hops N"
    if cmd == ":graph":
        return cmd_graph(a, arg.strip()) if arg.strip() else "usage: :graph <entity name>"
    if cmd == ":reset":
        a.reset()
        return "conversation state cleared"
    if cmd.startswith(":"):
        return f"unknown command {cmd}\n{HELP}"
    ans = a.ask(line)
    return f"{ans.text}\n  -- gate={ans.gate_status} method={ans.method}{' (fallback)' if ans.fallback else ''} citations={ans.citations}"


def main() -> None:
    a = Assistant()
    print(f"Connie-Lite  provider={a.llm.name}" + ("  (rule-based answers, no LLM)" if a.llm.name == "template" else ""))
    print(summary(a.store))
    print(HELP)
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        try:
            out = handle(a, line)
        except Exception as e:  # keep the REPL alive; details are in the trace
            out = f"error: {type(e).__name__}: {e}"
        if out is None:
            break
        print(out)
    sys.exit(0)
