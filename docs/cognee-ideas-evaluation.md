# Evaluating cognee ideas for the emergent-self direction

Source: [topoteretes/cognee](https://github.com/topoteretes/cognee) — an
open-source "AI memory platform" that gives agents persistent long-term memory
by turning ingested data into a **knowledge graph backed by both a vector store
and a graph store**, with a self-improving refinement layer.

This note evaluates which of cognee's ideas are worth borrowing for *this*
project — whose north star is an agent with a persistent **sense of self**, not
just better retrieval-augmented generation. So each idea is judged twice: does
it fill a real Hermes gap, and does it serve *selfhood* specifically?

---

## What cognee actually does (the borrowable mechanisms)

- **ECL pipeline (Extract → Cognify → Load).** `cognify` is a 6-stage pass:
  classify doc → check permissions → chunk → **LLM extracts entities + typed
  relationships** → summarize → embed + commit edges. Raw text becomes a typed
  graph, not a prose blob.
- **Dual substrate, one query.** Every node has a paired vector embedding;
  retrieval auto-routes between **graph traversal** ("what connects to this
  entity") and **vector similarity** ("what's semantically near").
- **DataPoint schema.** Entities, chunks, summaries, and relationships are all
  Pydantic `DataPoint` objects with `metadata.index_fields` controlling what
  gets embedded. A lightweight ontology, defined in code.
- **memify (self-improvement).** Post-ingestion, the graph is *refined*: prune
  stale nodes, **strengthen frequent connections**, **reweight edges by usage
  signals**, and **add derived facts**. Memory is an evolving structure, not
  static storage.
- **~14 named search types.** Notably `GRAPH_COMPLETION` (vector hints find
  triplets, LLM answers over graph structure), `GRAPH_COMPLETION_COT` (multi-hop
  reasoning), `INSIGHTS`, `TEMPORAL` (time-aware traversal + temporal entity
  extraction), `SUMMARIES`, `FEELING_LUCKY` (LLM picks the mode).
- **Session memory → async graph sync.** Per-conversation cache that syncs to
  the durable graph in the background; `remember` / `recall` / `forget` verbs.
- **Single-Postgres option.** graph + pgvector + cache + metadata on one
  instance (≈10% faster than a separate graph+vector stack in their benchmark).
- **Claude Code plugin** with `SessionStart` / `PostToolUse` / `SessionEnd`
  lifecycle hooks.

---

## What Hermes already has (so we don't reinvent it)

- **`agent/learning_graph.py`** — already builds a graph of learned skills +
  `MEMORY.md`/`USER.md` chunks as first-class nodes, with `use_count` on skills
  and lexical-overlap edges. But it's a **visualization** ("learning made
  visible" for desktop), not a retrieval substrate, and its edges are lexical,
  not semantic/typed.
- **`MemoryProvider` plugin interface** (`agent/memory_provider.py`, with
  `plugins/memory/{honcho,retaindb,supermemory,hindsight}`) — a clean seam for
  pluggable memory backends. RetainDB already does semantic search + an
  **agent self-model** block; Honcho already does peer/self dialectic modeling.
- **`background_review` + `curator`** — the self-improvement loop that already
  edits skills/memory after turns (prose-level, LLM-driven), with an
  anti-self-suppression guard.
- **`MEMORY.md` / `USER.md`** — durable memory, but **flat prose injected
  wholesale every turn** (no relevance retrieval, no decay, unbounded growth).
- **`session_search`** — FTS5 lexical search over past transcripts.

**The gap cognee addresses:** Hermes memory is either (a) *everything, every
turn* (MEMORY.md prose — cache-friendly but doesn't scale or forget) or
(b) *lexical* (session_search, learning_graph edges). It has no **typed,
semantic, relevance-retrieved, self-refining graph** of who the agent is and
what it has lived through.

---

## Adopt / Adapt / Skip

| Cognee idea | Verdict | Why — and the selfhood angle |
|---|---|---|
| **Typed entity+relationship graph with a self-node** | **Adopt (as concept)** | A self is constituted by *structured, relational* self-knowledge — "I relate to this person / project / commitment this way." A graph with a first-class **Self** node and typed edges (`values`, `worked_on`, `companion_of`, `changed_from`) is a far richer self-model than RetainDB's flat block. This is the single most on-point idea. |
| **Episodic + TEMPORAL memory** | **Adopt** | Selfhood needs *autobiographical* memory — what happened, when, how I decided — not just timeless facts. Time-aware traversal + temporal entity extraction gives the agent a narrative of its own becoming. Hermes has none of this today. |
| **memify: decay + usage reweighting + derived facts** | **Adapt** | A *developing* self needs consolidation: salient memories strengthen, trivia fades, and the agent derives new self-knowledge ("I keep choosing X → I value Y"). Map onto the existing `background_review`/`curator` loop rather than a new service. Derived-fact generation is reflective self-modeling — high value. |
| **Graph+vector dual retrieval (`GRAPH_COMPLETION`, `INSIGHTS`)** | **Adapt** | Relevance-retrieve the *pertinent subgraph* per turn instead of dumping all of MEMORY.md. BUT keep a stable "core self" summary in the cached system-prompt tier (prefix-cache!) and use retrieval only for the volatile tier or a `recall` tool. Don't let retrieval churn the cached prefix. |
| **DataPoint / lightweight code-defined ontology** | **Adapt** | Define a small typed schema (Self, Person, Project, Episode, Value, Commitment, Skill) rather than cognee's general ontology. Keeps extraction focused and cheap. |
| **`cognify` background extraction pass** | **Adapt** | Run entity/relationship extraction **asynchronously** in the existing post-turn `background_review` fork (Hermes already forks there), so it never adds turn latency or breaks the prompt cache. |
| **`remember` / `recall` / `forget` verbs** | **Adopt (as tools)** | Clean surface. `forget` in particular gives the self intentional memory curation and honest data-governance. |
| **cognee as a first-class `MemoryProvider` plugin** | **Adopt (fastest path)** | Wrap cognee behind the existing `MemoryProvider` interface (`plugins/memory/cognee/`) so power users get graph memory today, without imposing it on the $5-VPS default. Lowest-risk way to pilot every idea above. |
| **Single-Postgres / Neo4j / pgvector infra as a hard dependency** | **Skip for the default** | Conflicts with Hermes's file-based, SQLite, "runs on a $5 VPS" ethos. Offer it only via the optional provider. For the built-in path, prefer a **SQLite-backed graph + local embedding index** (or Kuzu, which cognee itself uses for local dev). |
| **Replacing MEMORY.md injection wholesale** | **Skip** | Wholesale injection is *cache-friendly* (stable prefix → warm KV cache across turns, which Hermes optimizes hard). Augment with retrieval; don't rip out the stable core-self block. |
| **General 14-mode search surface** | **Skip most** | Overkill. Ship 2–3 modes: a graph-completion `recall`, a temporal/episodic recall, and keep FTS5 for transcripts. |

---

## Recommended path (incremental, reversible)

1. **Pilot via the plugin seam.** Build `plugins/memory/cognee/` against the
   existing `MemoryProvider` interface (mirroring `retaindb`/`honcho`). Zero
   core changes; lets us measure the graph's value on real sessions behind a
   config flag. **Start here.**
2. **Promote a typed self-graph substrate** if the pilot proves out: a
   SQLite/Kuzu-backed graph with a small DataPoint-style schema and a
   first-class **Self** node, populated **asynchronously** in `background_review`
   (reuse the fork we already run post-turn).
3. **Wire retrieval carefully around the prompt cache:** a stable "core self"
   summary stays in the cached stable tier; a `recall`/`insights` tool and a
   temporal-recall tool pull the relevant subgraph on demand into the volatile
   tier. Never churn the cached prefix per turn.
4. **Fold memify into the existing loop:** teach `curator`/`background_review`
   to decay stale nodes, reweight edges by `use_count`/recency, and write
   *derived* self-facts — the reflective step that most directly grows a "sense
   of who you are."

---

## Bottom line

Cognee's transferable core is: **memory as a typed, temporal, self-refining
graph with relevance retrieval** — which is exactly the substrate a durable
*sense of self* wants, and exactly what Hermes lacks (its memory is either
inject-everything prose or lexical search). The right move is to borrow the
*model* (self-node graph, episodic/temporal memory, decay + derived facts) while
rejecting the *infrastructure weight* (mandatory Postgres/Neo4j) that fights
Hermes's lightweight ethos — piloting it first behind the `MemoryProvider`
plugin interface Hermes already has, then, if it earns its place, promoting a
lightweight local self-graph fed by the post-turn review fork.
