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

## 3. OPEN WORK — refactoring (Phase 1 nearly done, 2026-07-17)

Full plan + evidence in **`docs/refactoring-opportunities.md`**.

**Environment is now fully wired (2026-07-17):** pyenv 3.12.0 (repo-local
`.python-version`, untracked — CI pins 3.11) + `uv sync --locked --extra all
--extra dev` (CI's exact recipe) → `.venv` with the whole pinned dep tree.
Run tests ONLY via `scripts/run_tests.sh <files>` — the suite assumes
per-file isolation; batching multiple test files into one bare `pytest`
process produces phantom cross-file failures.

**Full-suite baseline (first ever run, triaged 3-way in a pre-reframing
worktree):** 48 failures / 23 files out of 2,041 files. (a) 5 assertions
stale from the intentional reframing → fixed (`b258b6c7f`); (b) 4 files
flaky only under 16-way parallel load (lsp e2e, service_manager,
approved_command_clean_slate, local_interrupt_cleanup) — pass when run
directly; (c) the rest (~15 files, incl. anthropic_adapter
TestRunOauthSetupToken, state_db_malformed_repair, search_error_guard,
gateway_service/wsl, live_system_guard) fail identically at the
pre-reframing upstream commit on this platform — pre-existing, not ours.

### Phase 1 — DONE (one fold per commit, tests green each time)
1. ✅ `114d3554c` Cron ReDoS drift: canonical bounded `FILLER` export from
   `threat_patterns`, both cron tables import it; `skills_guard`'s literal
   `INVISIBLE_CHARS` copy collapsed to the canonical frozenset. NOTE: a real
   ReDoS regression test needs the near-miss filler words to BE alternation
   words ("ignore prior prior … notinstructions") — neutral filler backtracks
   linearly and proves nothing.
2. ✅ `ca27c7498` `tools/browser_boundary.py` (redaction walker +
   `secret_in_url_error`). Closed the secret-in-URL gap on TWO sibling paths:
   `camofox_navigate` (defense-in-depth; its only production call site was
   already post-guard) and **CDP `Page.navigate`, which was a live bypass**.
   The CDP check runs outside the guard's fail-open try/except.
3. ✅ `414ae34bc` truthy/falsy fold (9 sites; added `FALSY_STRINGS`/
   `is_falsy_value` for the default-on sites) · `23209a0a0` atomic-write
   holdouts (anthropic_adapter creds, bitwarden installer).
4. ✅ `3385a5dd3` AGENTS.md/CLAUDE.md twin loaders → `_load_first_named_md`.
   (The fuller "loader table" was judged overreach: `_load_hermes_md` and
   `_load_cursorrules` are structurally different; only the twins were dupes.)
- **Skipped deliberately:** `truncate_middle` fold — the three
  implementations share ~4 lines and their markers are model-visible
  behavior (byte-stable per ground rules); a shared helper is ceremony.
- **Remaining from Phase 1:** `main()` subparser extraction (item 4 —
  mechanical, large diff, pattern already underway: 86 `build_*_parser`
  refs). And the deferred §1.10 `get_setting`/`cfg_get` migration (44
  sites, each needs a precedence audit).

Phases 2 & 3 (CapabilityRegistry, CommandDef handlers, StopGuard, the
`run_conversation` 4,939-line split, model-capabilities table) are scoped in
the doc with risk notes. Threat-pattern 5-table full fold is Phase 2
(skills_guard verdicts aren't covered test-per-verdict).

---

## 4. SECURITY findings (surfaced by the refactor survey)

Bugs (a) and (b) below are **FIXED** (`ca27c7498`, `114d3554c` — see §3);
(c) child-env scrub consolidation remains, Phase 2/3. Historical detail:

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
  (the real third-party graph-memory codebase). **UNBLOCKED (2026-07-17): the
  full source is checked out locally at `../cognee`** (sibling of OotSim in
  the workspace) — read `cognify`/`memify` directly from there.
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

- **Deps ARE installed (2026-07-17).** pyenv 3.12.0 + `uv sync --locked
  --python ~/.pyenv/versions/3.12.0/bin/python3 --extra all --extra dev`
  → `.venv/` in the repo. The system `python3` is 3.9 — never use it (the
  codebase needs ≥3.11); always `.venv/bin/python` or `scripts/run_tests.sh`.
- **Run tests only via `scripts/run_tests.sh`** (per-file isolation).
  Batching several test files into one bare `pytest` process yields phantom
  failures (observed: 75 bogus failures that all pass isolated). Full suite
  ≈ 90 min on this machine; per-file runs are seconds.
- **Full-suite verification is DONE** — the reframing/rename are verified
  (5 stale prose assertions fixed in `b258b6c7f`); remaining failures are
  pre-existing upstream or parallel-load flakes (triage table in §3).
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

- Everything is on `main`; no PR (none requested). Working tree clean.
- 2026-07-17 session commits: `114d3554c` (cron ReDoS), `ca27c7498`
  (browser_boundary), `414ae34bc` (truthy fold), `b258b6c7f` (stale test
  assertions), `23209a0a0` (atomic writes), `3385a5dd3` (twin loaders),
  plus this handoff update.

## 8. Suggested first action for the next session

Working style (per the human, 2026-07-17): **optimize for LLM development —
no sprint/milestone ceremony.** The commit log is the process; one
verifiable fold per commit; machine-checkable state (this file, the sync
check, `scripts/run_tests.sh`) over narrative status.

Next up, in leverage order:
1. `hermes_cli/main.py` subparser extraction (Phase 1 item 4) — mechanical,
   continues the existing `build_*_parser` pattern, lowest-risk big win.
2. Phase 2 folds from `docs/refactoring-opportunities.md` §4: start with
   `CapabilityRegistry[T]` (tests pin behavior).
3. Decision confirmed by the human (2026-07-17): **refactor in place, no
   rewrite** — new-build only for genuinely new subsystems (self-memory
   graph vs `../cognee`, MoE later) against existing seams
   (`MemoryProvider`).
