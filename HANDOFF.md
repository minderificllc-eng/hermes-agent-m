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

## 3. REFACTORING — essentially COMPLETE (2026-07-17)

Full plan + evidence in **`docs/refactoring-opportunities.md`** (now
annotated in place with what shipped and which folds were deliberately NOT
done and why). ALL mega-items are now resolved — including the
`run_conversation` three-step split (see item 3 below). What remains is
only the optional low-value backlog listed at the end of this section and
the opportunistic helper adoptions in §8.

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
- ✅ `main()` subparser extraction COMPLETE (3 commits, 2026-07-17): all
  13 remaining inline blocks moved to `hermes_cli/subcommands/`;
  `main()` 1,977 → 538 lines; only the dynamic plugin-CLI loop stays
  inline. 8,686 hermes_cli tests green.
- ✅ **Oracle certified clean**: the full 2,041-file suite passes on this
  machine. Getting there surfaced and fixed SIX real macOS product bugs
  (temp-dir writes blocked as "sensitive path", verify-artifact rm
  exemption dead, SQLite repair broken under defensive mode, env
  snapshot TEAR from empty $BASHPID in bash 3.2, + test-infra gaps).
  Green now means green — treat any new failure as signal.
- ✅ `CapabilityRegistry[T]` fold COMPLETE (2026-07-17): the six
  ~90%-identical provider registries are thin modules over one generic
  (`agent/capability_registry.py`). Real differences became knobs
  (normalize/builtins, capability filter, fail-closed, no-single-
  shortcut + local sentinel). Modules keep import surface, loggers, and
  `_providers`/`_lock` aliases (tests mutate in place). 7,496
  agent+plugins tests green. NOTE: `browser_registry._resolve` has no
  production caller — `browser_tool._get_cloud_provider` still does its
  own resolution; unifying that is a candidate follow-up.
- ✅ `StopGuard` fold COMPLETE (2026-07-17): the 3 stop-guard injections
  in `conversation_loop.py` (verify-on-stop / pre_verify / kanban) share
  one `_apply_stop_guard` helper; the #55733 role-alternation invariant
  lives in one place. Nudge-build/logging stay per-guard.
- ✅ `_send_chunks` fold COMPLETE (2026-07-17): the 6 send_message media
  chunk-loops (Discord/Matrix/Signal/Yuanbao/Feishu/WhatsApp) → one
  helper + a per-platform send closure and `[]` vs `None` empty sentinel.
- ✅ tts_tool provider table COMPLETE (2026-07-17): the 11-arm built-in
  ladder (depth 16) → `_BuiltinTTS` table; parity-pinned to
  `BUILTIN_TTS_PROVIDERS` minus edge. edge stays the default branch.
- ✅ `select_provider_and_model` `_simple_flows` table COMPLETE
  (2026-07-17): 12 uniform-signature provider arms → a table; args=/
  special-shape arms stay explicit.
- ✅ §2.3 child-env scrub: RESOLVED AS A DRIFT-GUARD, not a merge (the
  three policies are deliberately different postures; merge would weaken
  the sandbox's default-drop). `TestProviderCredentialCrossDrift` pins
  the cross-consumer invariant. See doc §2.3.
- ✅ Oracle stayed green throughout — the full 2,041-file suite was
  certified clean earlier this session and every fold above ran its
  covering suites (agent/, plugins/, tools/, hermes_cli/) before commit.

### Remaining — the three HIGH-CARE mega-items (NOT mechanical folds)
Investigation this session repeatedly found the audit's "N copies → 1"
framing understates deliberate divergence (child-env §2.3, model-caps
§1.5 — both corrected in the doc). Treat the rest the same way: analyze
per-site, bootstrap characterization coverage, migrate incrementally.

1. ✅ **`CommandDef` dispatch (§1.4) — COMPLETE (2026-07-17).** Both
   ladders done. CLI: extracted the giant inline arm bodies into `_cmd_*`
   methods, then converted the 71-branch elif chain to two tables
   (`_slash_command_tables`: `returning` by method-name via getattr,
   `delegates` as lambdas) — `process_command` went **663 lines / depth
   79 → 43 lines / depth 1** (the codebase's worst function is now
   trivial). Gateway: the 45 uniform `if canonical == X: return await
   self._handle_X_command(event)` arms → `_GATEWAY_UNIFORM_COMMANDS` table
   + one getattr dispatch; 7 special arms (new/start/learn/blueprint/undo/
   steer/moa) stay explicit. Per-class tables (NOT shared handlers on the
   frozen registry) because cli/gateway handlers are sync-vs-async on
   different classes — confirmed the right call. `test_slash_dispatch_
   tables.py` pins CLI coverage; brittle `getsource(_handle_message)`
   command-literal tests repointed to the table. 9,752 cli + 9,181 gateway
   tests green.
2. ✅ **model-capabilities (§1.5) — PROMPT-SIDE DONE (2026-07-17).** The
   prompt-shaping family checks (tool-use enforcement, developer role,
   Google/OpenAI operational guidance, edit-format family) are consolidated
   behind `agent.model_capabilities.model_capabilities(model) -> ModelCaps`;
   3 consumers migrated (system_prompt, chat_completions ×2). Pure
   re-exposure, characterization-pinned across a 19-model matrix. **The
   WIRE-SIDE stays deliberately separate and is NOT a TODO** — the bare
   `"claude"` checks are context-specific (wire format / cache envelope /
   header route); `agent_runtime_helpers` splits `is_claude` from
   `is_anthropic_wire` because Kimi/Moonshot on OpenRouter use Claude's
   cache envelope. A naive `is_anthropic_model()` merge silently serves 0%
   cache hits / re-bills every turn. This is a design fact, not incomplete
   work — see the doc §1.5 ⚠️ note and `model_capabilities.py`'s SCOPE
   docstring.
3. ✅ **`run_conversation` split (§3) — COMPLETE (2026-07-17), all 3 steps:**
   - ✅ (a) `_finalize_turn()` DONE: all 23 exits through one helper;
     `**extra` preserves each exit's EXACT key set (AST-verified). NOTE:
     the 23 dicts share 4 core keys but vary in flags, so the helper
     spreads `**extra`, NOT a normalized superset.
   - ✅ (b) resolved as ALREADY-DONE + DOCUMENTED-REJECTED remainder: the
     "TurnAttempt object" exists as `TurnRetryState` (upstream refactor,
     ~16 one-shot guards); its docstring deliberately keeps loop-control
     counters as locals. Deeper: `compression_attempts` is TURN-lifetime
     while `TurnRetryState` is PER-ATTEMPT — the audit's proposed move
     would reset the counter every API call and cause infinite compression
     loops on persistent 413s. Trap #6; see doc §3 table entry.
   - ✅ (c) DONE: `_try_error_recovery()` — the 12 one-shot recovery arms
     (image-shrink, multimodal-strip, oauth-1M-beta, five 401 credential
     refreshes with diagnostics, thinking-signature, invalid-encrypted,
     llama-grammar) extracted verbatim, `continue`↔`return True` 1:1
     audited (inner for-loops contain no continue), ordering preserved.
     run_conversation: 4,911 → 4,421 lines. Per-arm behavioral tests +
     full agent/ + run_agent/ (7,689) green.

- ⬜ **§1.10 remaining migration:** the `get_setting` HELPER is DONE (added
  + tested). The per-site adoption is NOT uniform — many sites use
  `os.getenv(X) or cfg...` (falsy-fallthrough) which differs from
  `get_setting`'s None-based presence check; each needs a falsy-vs-None
  audit. Migrate opportunistically, not blind find-replace.

**Method note carried forward:** this session repeatedly found the
audit's "N copies → 1" framing understated deliberate divergence
(child-env §2.3, model-caps §1.5, run_conversation exit key-sets). Before
any "merge N into 1", read all N and confirm they're actually the same —
several weren't, and a naive merge would have shipped a silent
security/billing/behavior regression. When they differ, the right move is
often a drift-GUARD test (child-env) or a knob-parameterized generic
(CapabilityRegistry), not a flattening merge.

Still unclaimed from the original audit (lower value, all optional):
threat-pattern 5-table FULL fold (skills_guard's 118 verdicts aren't
covered test-per-verdict — the ReDoS/INVISIBLE_CHARS drift is already
fixed), plugin-category loader dedup, kanban per-tool schema boilerplate,
`init_agent` phase extraction + `agent_init↔run_agent` residue,
`browser_registry._resolve` unification into `browser_tool._get_cloud_provider`.

---

## 4. SECURITY findings (surfaced by the refactor survey)

ALL RESOLVED: (a) and (b) fixed (`ca27c7498`, `114d3554c`); (c) resolved
as a cross-drift guard test, NOT a merge — see §8 trap #1. During (a)'s
fix a THIRD instance surfaced and was closed: CDP `Page.navigate` was a
live secret-in-URL bypass. Historical detail:

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

- Everything is on `main`, pushed to `origin/main` (kept in sync commit-by-
  commit — that's the standing policy). No PR. Working tree clean except
  untracked `.python-version` (intentional: CI pins 3.11, local is 3.12).
- The 2026-07-17 marathon session landed **~40 commits**: security drift
  fixes, oracle certification (6 real macOS product bugs), `main()` +
  `process_command` + gateway-ladder decomposition, CapabilityRegistry /
  StopGuard / send-chunks / tts-table / provider-flows / model-capabilities
  folds, `_finalize_turn`, `_classify_send_error`, `get_setting`, and the
  drift-guard tests. `git log` is the authoritative record — commit
  messages carry the full rationale including the traps avoided.
- **Attribution policy (standing, from the human):** commits/PRs carry NO
  Co-Authored-By or AI attribution — Minderific, LLC only. Git identity is
  already `Minderific, LLC <minderificllc@gmail.com>`.

## 8. What the next session should do

Working style (per the human, standing): **optimize for LLM development —
no sprint/milestone ceremony.** The commit log is the process; one
verifiable unit per commit, pushed immediately; machine-checkable state
(this file, `scripts/run_tests.sh`, the identity sync check in §6) over
narrative status. On friction, build the missing support (tests, harness,
tooling) instead of grinding. Under ambiguity, first-principles decision,
then commit to it.

### ⚠️ Negative knowledge — traps found and dodged this session (READ FIRST)

Five times, the refactoring audit's "N copies → fold into 1" framing
understated *deliberate* divergence. Each near-miss is documented at the
site and in `docs/refactoring-opportunities.md`; do NOT re-attempt:

1. **Child-env scrub merge (§2.3)** — the 3 policies are different postures
   (code_execution is default-DROP, strictly stronger). Merging WEAKENS the
   sandbox. Resolved with `TestProviderCredentialCrossDrift` instead.
2. **`is_anthropic_model()` (§1.5 wire-side)** — `is_claude` vs
   `is_anthropic_wire` are deliberately split (Kimi/Moonshot on OpenRouter
   use Claude's cache envelope). A merge silently serves 0% cache hits and
   re-bills every turn. Prompt-side is consolidated; wire-side is a design
   fact, not a TODO.
3. **§1.9 Discord "bespoke retry"** — doesn't exist; its rate-limit code
   serves command-sync/interactions. The fix was the `_classify_send_error`
   hook, not deletion.
4. **§1.10 blind `get_setting` migration** — existing `os.getenv(X) or
   cfg...` sites are FALSY-fallthrough; `get_setting` is None-based. Blind
   replacement changes empty-string/`0`/`False` behavior. Audit per site.
5. **`truncate_middle` fold** — the 3 implementations share ~4 lines and
   their markers are model-visible behavior. Skipped as ceremony.

Also hard-won environment/verification lessons:
- **Tests ONLY via `scripts/run_tests.sh`** — batching files into one bare
  pytest process yields phantom cross-file failures (75 observed).
- **Execute real behavior, don't model it**: the `$BASHPID` fix was
  "verified" by reasoning twice and wrong twice (bash 3.2 forks per `$()`
  expansion); the behavioral test running real `/bin/bash` caught it.
- ReDoS regression tests need adversarial inputs whose filler words ARE
  alternation words; neutral filler backtracks linearly and proves nothing.
- macOS-specific traps that keep appearing: `/tmp`→`/private/tmp` and
  `/var`→`/private/var` realpath asymmetry; Apple SQLite ships
  SQLITE_DBCONFIG_DEFENSIVE on; stock bash is 3.2 (no BASHPID); zombie
  processes pass `kill(pid, 0)`.

### Next work, in leverage order

1. **`run_conversation` split steps (b)+(c)** — the ONE remaining
   refactor mega-item; see §3 item 3 for the full scoping (TurnAttempt
   extraction; recovery-cascade strategy table — arms are entangled
   procedures, do ONE ARM AT A TIME with a provider-error repro each).
2. **Opportunistic adoptions** (safe, unbounded backlog): `cfg_get` for
   genuine config `.get().get()` chains; `get_setting` where a site's
   falsy-vs-None intent is confirmed; `model_capabilities()` for any new
   prompt-side family checks.
3. **The actual north star**: with the refactor substrate clean, the next
   frontier is the **self-memory graph** (cognee-inspired; source at
   `../cognee`, eval in `docs/cognee-ideas-evaluation.md`, pilot path =
   `plugins/memory/cognee/` behind the existing `MemoryProvider` seam) and
   later the human's MoE integration (other Minderific repos — do not
   infer its design from this one).
4. Decision confirmed by the human: **refactor in place, no rewrite** —
   new-build only for genuinely new subsystems against existing seams.
