# Connie-Lite

Connie-Lite is a conversational assistant that answers questions about a client (Solstice Robotics). It uses graph-augmented RAG over 28 annotated alert emails. Code builds a typed knowledge graph from the entity annotations and the client profile, and every edge records the alert(s) or profile entry behind it. For each question, a planner picks an intent and the entities involved. Retrieval walks the graph and collects the alert passages behind the edges it used. It has two generic traversals: a 1–2 hop walk around an entity, and bounded paths from an entity to a target. It also has named multi-hop templates for known question shapes. A sufficiency gate decides whether to answer, give a partial answer, or abstain. An answer is produced, and a validator checks every citation and every named entity against the evidence. The LLM is used in only two places, query planning and answer wording, and code validates its output both times. With no API key, a clearly labelled rule-based planner and extractive renderer run the whole pipeline.

```
 data/*.json
     │
 ingest ──► graph build (EDGE_RULES R1–R6, every edge = list of Supports: source + provenance)
                 │
 question ─► linker (exact n-gram + guarded fuzzy, anaphora) ─► planner (rule_plan | LLM, schema-constrained)
                 │                                                   │ QueryPlan: intent, entity_ids, target, hops
                 ▼                                                   ▼
            retrieve: NEIGHBORHOOD walk | CONNECT paths | named metapath TEMPLATES   (hub-routing guard)
                      + alert passages behind the kept edges (BM25 only ranks/trims text)
                 │
            gate: answerable | partial (what is missing + nearest evidence) | none (abstain, no LLM)
                 │
            generate: template renderer | LLM answer
                 │
            validate: citation ids ⊂ evidence · every sentence cited or "Not found:" ·
                      no company/person/regulator outside the evidence subgraph · discovered/annotation labels
                      (LLM: one retry with the errors, then fall back to the template renderer)
                 │
            state (last focus entities for pronouns) + per-turn JSON trace
```

## Setup

The project requires Python 3.11 or later.

```bash
python3.11 -m venv .venv && source .venv/bin/activate     # or: uv venv -p 3.11 .venv
pip install -r requirements.txt
```

## Run with no keys

```bash
python -m connie_lite          # REPL
python scripts/demo.py         # scripted 6-turn conversation -> demo_transcript.md
python eval/run_eval.py        # metrics table
pytest                         # tests
```

Answers from the template provider start with `(rule-based answer)`. No LLM is called.

REPL commands: `:why` (kept paths with supports), `:graph <entity>` (1-hop neighborhood with supports), `:hops N`, `:reset`, `:quit`. Every turn writes a JSON trace to `traces/`.

## Run with an LLM (Anthropic)

```bash
export LLM_PROVIDER=anthropic LLM_MODEL=claude-haiku-4-5 ANTHROPIC_API_KEY=...
# or: cp .env.example .env, edit it, then: set -a; source .env; set +a
```

- **Planner.** It uses Anthropic structured outputs (`output_config.format`), with a forced tool call as fallback. The JSON schema is built for each question, and `entity_ids` may only take values from a small candidate list: linker hits, the last focus entities, and the client.
- **Answer.** The model sees only the evidence block. If the answer fails validation, the model gets one retry with the validator errors. If that also fails, the deterministic renderer answers and the answer is marked `fallback=True`.
- **Recorded run.** `demo_transcript_anthropic.md` is a recorded run with `claude-haiku-4-5`.

### Replay mode

`REPLAY_MODE` controls the LLM cache:

| Mode | Behavior |
|---|---|
| `record` | Default with an LLM. Serves from `.cache/` when an entry exists. Otherwise it calls the model once and stores the output, so the first recording sticks and re-runs are identical. |
| `replay` | Serves only from the cache and raises `CacheMiss` otherwise. No network or key is needed, which is a safe way to run a live demo. |
| `off` | No caching. |

```bash
LLM_PROVIDER=anthropic LLM_MODEL=claude-haiku-4-5 REPLAY_MODE=replay python scripts/demo.py
```

## Layout

The package folders follow the pipeline. Each common change has one obvious file.

```
connie_lite/
  graph/                 BUILD THE GRAPH
    ingest.py            load data, normalise inconsistent entity keys, node types/ids, alias table, FOCAL_ID
    store.py             GraphStore protocol + NetworkxStore (swap for a graph DB here)
    rules.py             relation names + EDGE_RULES          <- add a relation here
    build.py             build_graph(): nodes, MENTIONS evidence layer, apply EDGE_RULES
  retrieval/             QUESTION -> EVIDENCE
    linker.py            entity linking (exact + guarded fuzzy) and pronoun detection
    planner.py           rule_plan / LLM planner -> validated QueryPlan
    traversals.py        generic graph walks: NEIGHBORHOOD, CONNECT (+ hub guard, metapath matcher)
    templates.py         named multi-hop question types       <- add a question type here
    text_index.py        BM25 over alert text (ranking, "nothing in corpus" check, eval baseline)
    evidence.py          run the finder, score paths, attach the alerts behind kept edges
    gate.py              answerable | partial | none, before any generation
  answer/                EVIDENCE -> ANSWER
    llm.py               LLMClient protocol, Anthropic + template clients, ReplayCache
    render.py            rule-based extractive answer (also the LLM fallback)
    generate.py          LLM prompt + flow: validate, retry once, fall back
    validate.py          citations, per-sentence coverage, no outside entities, honesty labels
  schema.py              shared records: Alert, Entity, Support, EdgeView, Path, Evidence
  assistant.py           one turn end to end + JSON trace (used by cli, demo, eval)
  state.py, config.py, cli.py
```

### Extending it

- **New relation.** Write a rule function in `graph/rules.py` and add it to `EDGE_RULES`.
- **New multi-hop question type,** for example competitor → market ← theme:
  1. In `retrieval/templates.py`, add the typed chain to `TEMPLATES`:
     `"COMPETITOR_THEME": [(COMPETES_WITH, "out", "Company"), (OPERATES_IN, "out", "Market"), (AFFECTS, "in", "Theme")]`
  2. Add a finder in the same file: `match_template` + `narrow_to_target`. Register it in `TEMPLATE_FINDERS`. The intent name becomes valid in the plan schema automatically.
  3. In `retrieval/planner.py`, add a keyword rule in `rule_plan` and one line in `PLANNER_SYSTEM`.

  Questions that no template covers are still answered by the generic `NEIGHBORHOOD`/`CONNECT` traversals.
- **Swap the graph backend.** Implement the `GraphStore` protocol in `graph/store.py`.
- **Add an LLM provider.** Write one class with `complete_json` and `complete_text` in `answer/llm.py`.

## Assumptions

- **Provenance weights.** `profile` 1.0 > `text` 0.9 > `annotation` 0.7 > `co_mention` 0.6. An edge's confidence is its best support. A path scores `Π confidence × 0.5^(days since newest support / 60)`, with recency measured from the newest alert in the corpus, not the wall clock. Profile-only paths get recency 1.0.
- **R1 client relationships.** A `related_to_focal` annotation creates the client → supplier/customer/competitor edge. Provenance is `text` when the alert text names Solstice and `annotation` when it does not (a09 Ferrotech, for example). An edge with no profile support has status `discovered`. In this corpus that means Hanley Precision Casting (a21) and Orion Freight Systems (a22).
- **R3 subject-company attribution.** In an alert that mentions companies, attribute entities (market, commodity, country, theme, regulator) attach to the non-focal companies. They attach to the client only when the client is the sole company. This is a co-mention heuristic: annotations are per alert, not per relation.
- **R4 context bridges.** Alerts with no company link regulators, commodities, and themes to the countries and markets they mention (`AFFECTS`, `RELATED_TO`). The 3-hop chain supplier → country ← regulator depends on these edges.
- **Hub-routing guard.** The client connects to almost everything through profile edges. When the question is about a non-client entity, paths may not pass through the client. Otherwise "Ferrotech's exposure to tariffs" would succeed through Ferrotech → Solstice → tariffs, which is the client's sensitivity, not Ferrotech's.
- **Generic entities.** A lower-case "company" name becomes a `Segment` node, not a `Company`. An example is "e-commerce fulfillment customers" (a01). Segments get no relation edges. "EU AI Act" stays a `Regulator` with `subtype=regulation`. "Federal Reserve" is a regulator that is not in the profile.
- **Noise alerts.** a23–a26 have no entities. They are left out of the graph but kept in the BM25 index.
- **`DISCOVERED` scope.** This intent considers only client relationship edges (supplier, customer, competitor). Executive and site edges are also non-profile, but they are not "relationships".
- **Free-text targets.** If a target term does not resolve to a graph node, for example "export controls" or "batteries", a template path is kept only if the alert text behind its final edge contains the term (rapidfuzz `partial_ratio` ≥ 90). Otherwise the gate reports the term as missing.
- **`BM25_MIN = 1.0`.** This value was set empirically. Off-topic questions ("weather in Paris") score 0.0. Questions that share only the client's name score below 1.0. One distinctive shared term scores above 1.2. The gate returns `none` only when there are no paths and no alert scores ≥ `BM25_MIN`.
- **Hop cap.** `MAX_HOPS` (default 2) is the default depth. The hard cap is 4. The supplier → country ← regulator template needs 3 hops, and the planner may request it.
- **Validator honesty labels.** In addition to the three required checks, the validator rejects two kinds of answer. The first names a newly discovered relationship without the phrase "newly discovered". The second names an annotation-only client relationship without saying that the alert text does not name the client. A live LLM run showed the model dropping this caveat when only the prompt asked for it.

## Evaluation

`python eval/run_eval.py` runs 10 hand-written items: the 6 demo turns as one conversation, plus 4 unanswerable questions.

```
metric                            template   claude-haiku-4-5
path recall                           1.00               1.00
answerable coverage                   1.00               1.00
citation coverage                     1.00               1.00
citation validity                     1.00               1.00
invented-entity rate                  0.00               0.00
abstention accuracy                   1.00               1.00
multi-hop recall@6 (graph)            1.00               1.00
multi-hop recall@6 (BM25 only)        0.43               0.43
perturbation (drop a09 -> Q1)         PASS               PASS
```

- **Graph vs BM25.** Graph retrieval finds every alert that a multi-hop answer needs. The BM25-only baseline finds under half, because the a09 magnet alert never mentions Solstice.
- **Perturbation.** Removing that one alert turns Q1 into a partial answer. The answer depends on the evidence, not on the model's prior knowledge.
- **Template scores.** With the template provider, the answer-level metrics are 1.0 by construction. The Haiku column measures a real model behind the same validator.
- **Validator activity.** During recording, the validator rejected several LLM drafts: uncited opening sentences and missing honesty labels. The retry, and occasionally the fallback, repaired them.

## Known limitations

- Entity annotations are per alert, not per relation. Co-mention edges (R3/R4) can misattribute when one alert mentions several companies, and every non-focal company in the alert gets the same attributes.
- Edges have no temporal invalidation. An old alert keeps supporting an edge forever, and recency only lowers its score.
- The alias table is hand-built from the profile. Aliases for non-profile entities come only from the linker's fuzzy matching, which accepts a capitalised prefix such as "Ferrotech" → Ferrotech Alloys.
- `rule_plan` is keyword-based. Paraphrases outside its rules fall back to the generic `NEIGHBORHOOD`/`CONNECT` traversals. The answers stay grounded but are less targeted, and the LLM planner handles paraphrases better.
- The validator checks citation ids, not whether the cited alert actually supports each claim. Sentence-level entailment would be the next check to add.
