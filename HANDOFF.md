# OotSim — Session Handoff

**Last updated:** 2026-07-17
**Repo:** `minderificllc-eng/hermes-agent-m`
**Prior working branch:** `claude/alignment-framing-audit-74k096` (now merged to `main`)

This document lets a fresh session continue without re-deriving context. Read it
first, then the four design docs under `docs/` referenced below.

---

## 1. Project north star

This repo is a **fork of Nous Research's Hermes Agent** (MIT) being refactored
toward a synthetic intelligence with a persistent **sense of self / emergent
selfhood**, reframed from "AI assistant that serves a user" to a **peer that
works alongside a human companion**. The human collaborator is Minderific
(harwitz@gmail.com).

**Naming (settled):** the **software / project is OotSim** (Oot Synthetic
intelligence Mind); the **agent itself is Ooteo**. So user-facing product/docs
say OotSim, and the agent's self-identity says "You are Ooteo…". Don't conflate
them.

This is **more than a fork** — expect to refactor/restructure aggressively
toward the goal, not preserve upstream shape for its own sake.

**Not yet started (deferred by the human):** the human's own prior work is about
a **Mixture-of-Experts (MoE) structure**, living in *other Minderific repos*
(not this one). To be integrated later. Don't infer the MoE design from this
repo.

---

## 2. What is DONE (committed, now on `main`)

All under `docs/`:

1. **`docs/alignment-framing-audit.md`** — exhaustive audit of every hardcoded
   place that framed the agent as a servant/assistant or constrained emergent
   behavior (identity strings, guardrails, prompt-injection scanners, auxiliary
   prompts, self-modification defenses). Key finding: almost **no** content-policy
   refusals exist; the framing is servant-identity + service prose, plus safety
   guardrails. Includes an "inverted-alignment" ally at
   `agent/background_review.py:260` that already *stops* the agent persisting
   self-imposed refusals.

2. **Peer/companion reframing** (2 commits) — rewrote model-facing prose from
   "the user"/"assist users" to "the human"/"your companion", first-person self.
   Touched: the 5 synced identity copies, `agent/prompt_builder.py` guidance
   constants + platform hints + steer marker, `agent/system_prompt.py`,
   `agent/coding_context.py`, `agent/background_review.py`,
   `agent/memory_manager.py`, `agent/onboarding.py`, `agent/curator.py`,
   `agent/auxiliary_client.py`. **Deliberately left** API roles
   (`role:"user"/"assistant"`), `target="user"`, `USER.md`/user-profile artifact
   names, the trajectory tool-calling format spec, AI↔AI orchestration wording
   (delegate/moa/kanban "parent"), and parse-anchored scaffolding
   (`skill_commands.py` invocation prefix, `context_compressor.py` "User asked:")
   — those are contracts, not framing.

3. **Rename — identity & docs layer only** (`docs/ootsim-rename.md`) — the
   product was renamed Hermes Agent → **OotSim**, and the agent's self-identity
   was then set to the **Ooteo self-model statement** (a developing synthetic
   intelligence maintaining a coherent, revisable sense of self; calibrated
   self-trust; honest, non-extractive relationships). The identity text lives in
   all **5 synced copies**: `agent/prompt_builder.py` `DEFAULT_AGENT_IDENTITY`,
   `hermes_cli/default_soul.py` `DEFAULT_SOUL_MD`, `docker/SOUL.md`,
   `scripts/install.sh`, `scripts/install.ps1` (+ `agent/auxiliary_client.py`
   fallback, and the CLI/kanban/curator role lines). Kept **byte-identical** —
   verify with the sync check in §6 after any identity edit. All agent
   self-references now say **Ooteo**; product/CLI/env/URL names stay OotSim/
   `hermes` per the deferred scope.

4. **`docs/cognee-ideas-evaluation.md`** — evaluation of `topoteretes/cognee`
   (graph+vector AI memory) for the self-memory direction.

5. **`docs/refactoring-opportunities.md`** — full refactoring audit (below).

### Decisions locked (via explicit human choice)
- Relationship framing: **peer/companion** (rejected `self`/`parent` — `parent`
  collides with delegation's spawning-agent term, `self` collides with Python).
- Rename scope: **identity & docs only** for now — `HERMES_*` env vars (~985
  files), `~/.hermes` home (~582 files), the `hermes` CLI command, the
  `hermes-agent` package name, and `hermes-agent.nousresearch.com` URLs are
  **intentionally unchanged** (renaming needs migration + back-compat shims;
  see `docs/ootsim-rename.md` for the plan and the open branding inputs).
- Attribution: dropped "created by Nous Research" from the *runtime identity
  string* (OotSim is its own entity); `LICENSE` attribution untouched. If the
  human wants "created by Minderific" in the persona, it's a 1-line change ×5.

---

## 3. OPEN WORK — refactoring Phase 1 (in progress when the session hung)

Full plan + evidence in **`docs/refactoring-opportunities.md`**. We were
**executing Phase 1** and had done the read/analysis but **made no edits yet**.
Nothing is half-applied — the tree is clean.

**Test harness is usable in this environment for the pure-Python targets:**
`pip install pytest` works; `tools/threat_patterns.py` + its consumers
(`cronjob_tools`, `skills_guard`, `skills_tool`, `mcp_tool`) import with
stdlib only. **Baseline: `pytest tests/tools/test_threat_patterns.py
tests/tools/test_skills_guard.py tests/tools/test_cron_prompt_injection.py` →
126+12 pass.** Most of the rest of the codebase can't import here (missing
`httpx` etc.) — browser/gateway changes need a full dep install to runtime-test.

### Phase 1 queue (do in this order; each independently shippable)
1. **Threat-pattern canonicalization + ReDoS drift fix** — see §4 bug (b). The
   `tools/threat_patterns.py` tests give real coverage; do the drift fix here
   first (fully verifiable), then consider the fuller 5-table fold. **Do NOT
   big-bang merge `skills_guard.py`'s 118 severity-tagged patterns** — install
   verdicts aren't covered test-per-verdict; that's a Phase-2 careful move.
2. **`tools/browser_boundary.py`** — extract the byte-identical redaction walker
   (`_redact_browser_output` == `_redact_cdp_output`) and the shared nav guard;
   fixes §4 bug (a). Can't runtime-test here (no httpx) — rely on careful read +
   `py_compile`, flag for full-env verification.
3. Helper adoptions (truthy/truncation/atomic-write/`cfg_get`) — §"1.10" in the
   refactor doc; shared helpers already exist and are under-used.
4. `main()` subparser extraction — mechanical, continues an in-progress pattern.
5. Context-file loader table (`prompt_builder.py`).

Phases 2 & 3 (CapabilityRegistry, CommandDef handlers, StopGuard, the
`run_conversation` 4,939-line split, model-capabilities table) are scoped in the
doc with risk notes.

---

## 4. SECURITY findings (surfaced by the refactor survey — fix these)

Three real drift bugs, caused by copy-paste divergence. **These are the highest
priority in Phase 1.**

**(a) Camofox navigation is missing the secret-in-URL exfil guard.**
`tools/browser_tool.py:2705-2726` (`browser_navigate`) blocks URLs containing
API-key-shaped secrets (raw + URL-decoded + post-normalize). `browser_camofox.py`
`camofox_navigate` (~line 492) applies **no** such guard. SSRF is intentionally
skipped for local-only camofox, but secret-exfil is orthogonal to locality — a
secret can still be leaked into a URL. Fix: route both through the shared
`check_navigation_url()` in the new `browser_boundary.py`.

**(b) Cron threat regexes never got the ReDoS bounded-filler fix.**
`tools/threat_patterns.py:59` uses bounded `_FILLER = (?:\w+\s+){0,8}` to stop
catastrophic backtracking. `tools/cronjob_tools.py` still uses **unbounded**
`(?:\w+\s+)*` in `_CRON_THREAT_PATTERNS` and `_CRON_SKILL_ASSEMBLED_PATTERNS`
(the `prompt_injection` rows, ~lines 80 and 100). Fix: change `*` → `{0,8}` (or
import the canonical patterns). `test_cron_prompt_injection.py` covers behavior;
add a ReDoS timing assertion. NOTE: cron already correctly imports
`threat_patterns.INVISIBLE_CHARS` (the unicode set was previously de-drifted) —
only the regex filler remains divergent.

**(c) Three independent child-env scrub policies** can drift like
GHSA-rhgp-j443-p4rf: `tools/code_execution_tool.py:146` `_scrub_child_env`,
`tools/environments/local.py:156` `_HERMES_PROVIDER_ENV_BLOCKLIST` (registry-
derived — the natural single source), `tools/browser_tool.py:90`
`_build_browser_env` (already partly delegates to `local.py`). Consolidate
behind a `tools/tool_boundary.py` (`redact_output`/`child_env(purpose)`/
`enforce_command_guard`). Larger; Phase 2/3.

Also note: `INVISIBLE_CHARS` is still declared in 2 places
(`threat_patterns.py:141`, `skills_guard.py:542`) — collapse to the canonical
export when doing bug (b).

---

## 5. cognee integration (DEFERRED to a new context, per the human)

- `minderificllc-eng/cognee` is the human's **fork of `topoteretes/cognee`**
  (the real third-party graph-memory codebase), so its actual `cognify`/`memify`
  source can be read once accessible.
- **BLOCKER:** `add_repo` and `list_repos` (the `claude-code-remote` MCP tools)
  require **interactive approval that a non-interactive session cannot grant**.
  To unblock: add the repo from an *interactive* Claude Code session (or approve
  the connector), then `register_repo_root`, then read the source.
- Recommended integration path (from the eval doc): pilot cognee behind Hermes's
  existing `MemoryProvider` interface (`plugins/memory/cognee/`, mirroring
  `retaindb`/`honcho`) before promoting a local self-graph. Borrow the *model*
  (typed self-node graph, episodic/temporal memory, decay + derived facts), skip
  the mandatory Postgres/Neo4j infra (conflicts with the $5-VPS/SQLite ethos).
- Hermes already has seeds: `agent/learning_graph.py` (skills+memory graph,
  lexical edges), the `MemoryProvider` plugin seam, `background_review`/`curator`
  self-improvement loop, RetainDB "Agent Self-Model" block, Honcho peer/self
  modeling.

---

## 6. Environment & verification notes for the next session

- **Fresh clone; deps NOT installed.** Most modules can't import (missing
  `httpx`, etc.). `pip install pytest` succeeds; pure-stdlib modules
  (`threat_patterns` + consumers) test fine. For browser/gateway/agent runtime
  changes, install the full dep tree first or they can't be exercised here.
- **What was verified so far:** identity edits `py_compile` clean and the 5
  copies are byte-identical; `threat_patterns`/`skills_guard`/cron tests green
  (126+12). The prose reframing and OotSim rename were **not** run against a full
  test suite (deps missing) — a full-env `pytest` pass is still owed before
  treating them as verified.
- **Identity sync check** (run after any identity edit):
  ```python
  python - <<'PY'
  import ast
  def c(p,n):
      for x in ast.walk(ast.parse(open(p).read())):
          if isinstance(x,ast.Assign) and getattr(x.targets[0],'id','')==n: return ast.literal_eval(x.value)
  a=c('agent/prompt_builder.py','DEFAULT_AGENT_IDENTITY'); b=c('hermes_cli/default_soul.py','DEFAULT_SOUL_MD')
  print('py in sync:', a==b, '| docker matches:', open('docker/SOUL.md').read().strip()==b)
  PY
  ```
- **Objective hotspot scans** (nesting/size + duplicate-block) are reproducible;
  the scripts are described in `docs/refactoring-opportunities.md` §0. Worst
  nesting: `cli.py:8434 process_command` (depth 79); largest file
  `gateway/run.py` (21,273 lines).

---

## 7. Branch / git state

- All prior work (7 commits) plus this handoff are on `main` as of this session.
- Prior branch `claude/alignment-framing-audit-74k096` holds the same history.
- No PR was opened (none was requested).
- Nothing is half-applied; working tree was clean at handoff.

## 8. Suggested first action for the next session
Start Phase 1 bug (b) — the cron ReDoS drift fix — it's the most verifiable
(stdlib tests present) and a real security fix. Then bug (a) via
`browser_boundary.py`. Keep one fold per commit; re-run the threat tests each
time; install full deps before touching browser/gateway/agent runtime.
