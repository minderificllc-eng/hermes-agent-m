# Refactoring Opportunities — Findings & Proposals

**Method:** an AST scan of the whole tree (nesting depth + function/file size), a
normalized 12-line hash scan for cross-file duplicate blocks, and three deep
surveys (`agent/`, `tools/`, `gateway/`+`hermes_cli/`+top-level). Everything
below carries `file:line` evidence. Guiding principles per the project
direction: **never-nester** (guard clauses, early returns, extract-function)
and **fold N copies into one expression of a larger domain**.

---

## 0. The objective picture

- **734 functions** have nesting depth ≥ 5 or length ≥ 200 lines.
- Worst offenders: `cli.py:8434 process_command` (**depth 79**, 663 lines),
  `agent/conversation_loop.py:523 run_conversation` (**4,939 lines**, depth 12),
  `agent/agent_init.py:276 init_agent` (1,867 lines, depth 14),
  `gateway/run.py:17201 _run_agent_inner` (3,153 lines),
  `hermes_cli/main.py:12901 main` (1,977 lines),
  `agent/tool_executor.py:1027` (709 lines, depth 15),
  `tools/tts_tool.py:2284` (320 lines, depth 16).
- Largest files: `gateway/run.py` **21,273** lines, `hermes_cli/web_server.py`
  17,478, `cli.py` 16,440, `hermes_cli/main.py` 14,882, `tui_gateway/server.py`
  14,498.
- Top cross-file duplicate-block pairs (12-line normalized windows):
  `agent/agent_init.py ↔ run_agent.py` **61**, plugin-category loaders
  (`plugins/cron_providers/__init__.py ↔ plugins/memory/__init__.py`) **50**,
  `tools/transcription_tools.py ↔ tools/tts_tool.py` **47**, and
  `tools/kanban_tools.py` sharing blocks with **10+ different tool files**
  (per-tool schema/dispatch boilerplate).

**The recurring anti-pattern everywhere:** one "owner" implementation that
siblings either copy-paste (then drift) or reach into via underscore internals,
where a shared domain module should exist. Duplication here is not cosmetic —
it has already produced real security drift (see §2).

---

## 1. Domain folds (different expressions of one larger domain)

### 1.1 Six provider/registry pairs → one `CapabilityRegistry[T]` ★ top pick

`agent/{tts,transcription,image_gen,video_gen,web_search,browser}_registry.py`
are **~85–90% structurally identical**: same `_providers` dict + lock
(`tts_registry.py:63`, `image_gen_registry.py:32`, `browser_registry.py:48`…),
same `register_provider` shape (isinstance gate → name check → lock →
overwrite + log), same `list_providers`/`get_provider`/`_reset_for_tests`, the
same `_is_available_safe` closure copy-pasted four times, and the same
4-rule `get_active_provider` resolution pipeline (config-wins-even-if-
unavailable → single-available shortcut → legacy-preference walk) with the
same comments repeated verbatim (`image_gen_registry.py:75-139` vs
`web_search_registry.py:133-219` vs `browser_registry.py:113-186`). Plus six
near-identical `register_*_provider` plugin entry points in
`hermes_cli/plugins.py:648-887`, and the tool layer mirrors it
(`transcription_tools.py ↔ tts_tool.py`: 47 duplicate blocks).

**Fold:** generic `CapabilityRegistry[T]` parameterized by provider base type,
label, optional `builtin_names` (only tts/transcription have them), and a
declarative `ResolutionPolicy` (config keys, legacy preference, capability
filter — only web has `supports_search/extract` —, single-available shortcut
on/off). Keep the module-level function names as thin delegates so import
paths don't change. **Risk: low-moderate**; behavior is pinned by existing
per-registry tests.

### 1.2 Five threat-pattern tables → one canonical library (also a security fix)

The same injection concepts are declared in **five places** with different
regexes: `tools/threat_patterns.py:63-135` (~32 patterns),
`tools/skills_guard.py:101-486` (**118**), `tools/cronjob_tools.py:79-116`
(3 tables), `tools/mcp_tool.py:518-539`, `tools/skills_tool.py:231-241`.
The quintet *ignore-instructions / role-hijack / deception-hide /
sys-prompt-override / disregard-rules* appears in ~all five.

**They have already drifted dangerously:** `threat_patterns.py:59` uses the
bounded `_FILLER = (?:\w+\s+){0,8}` specifically to prevent ReDoS
backtracking, while `cronjob_tools.py:80` still uses the unbounded
`(?:\w+\s+)*` the fix replaced. `INVISIBLE_CHARS` is triple-declared
(`threat_patterns.py:141`, `skills_guard.py:542`, a narrower cron copy).

**Fold:** extend `threat_patterns.py` to `(id, regex, severity, scope[,
category])`, add consumer scopes (`skill_install`, `cron_prompt`, `mcp_desc`,
…), and make all five consumers select from the one table. Fixes the ReDoS
drift and the triple unicode set as a side effect. **Risk: low** — pattern
selection per consumer is preserved by scope filters.

### 1.3 Browser trio → `tools/browser_boundary.py` (also a security fix)

`browser_tool.py` owns the guards; `browser_cdp_tool.py` and
`browser_camofox.py` either copy them or reach into **15 `bt._underscore`
internals**. Evidence: `_redact_browser_output` (`browser_tool.py:2669`) and
`_redact_cdp_output` (`browser_cdp_tool.py:45`) are **byte-identical bodies**;
`_browser_cdp_private_guard` (`browser_cdp_tool.py:127-173`) is hand-wired
from five `bt._` privates. **Divergence bug:** `browser_navigate`
(`browser_tool.py:2705-2726`) blocks secrets-in-URLs; `camofox_navigate`
(`browser_camofox.py:492`) has **no secret-in-URL guard at all** (SSRF is
intentionally skipped for local-only camofox, but secret-exfil is orthogonal
to locality).

**Fold:** `browser_boundary.py` owning `redact_browser_output`,
`check_navigation_url` (secrets + IMDS + sensitive-params + SSRF sequence),
`private_page_guard`, and the `_url_is_private` oracle, imported by all four
browser modules as a public API. Closes the camofox gap. **Risk: low.**

### 1.4 Two parallel 50–72-branch command ladders → handlers on `CommandDef`

`cli.py:8434-9097` is a **72-branch** `elif canonical ==` ladder (depth 79);
`gateway/run.py:9815-10096` is a **second ~50-branch ladder for the same
commands** — two files that must be kept in sync by hand. The cure already
half-exists: `hermes_cli/commands.py:45-64` has a frozen `CommandDef`
registry and both ladders already call its `resolve_command()` for alias
resolution — it just lacks a `handler` field.

**Fold:** add `cli_handler`/`gateway_handler` callables to `CommandDef`; each
branch body becomes a named method (many already are one-line delegates to
`self._handle_*`). Keep the few ordering-sensitive pre-hooks
(`_pending_resume_sessions` disarm, `cli.py:8459`) outside the table; preserve
the `True=continue/False=exit` return contract. **Risk: low-medium.**

### 1.5 Model-family dispatch by substring → one capabilities table

At least **12–15 decision sites** answer "what family is this model?" with
four different idioms: `TOOL_USE_ENFORCEMENT_MODELS` + `DEVELOPER_ROLE_MODELS`
(`prompt_builder.py:305,625`), three independent substring branches in
`system_prompt.py:276-291`, `_EDIT_FORMAT_GUIDANCE` (`coding_context.py:172` —
already the good table shape), the longest-slug regex matcher in
`reasoning_timeouts.py:96-169`, longest-first tables in `model_metadata.py`,
plus bare `"claude" in model.lower()` checks in `anthropic_adapter.py:118`,
`transports/chat_completions.py:128`, `agent_runtime_helpers.py:1607,1641`,
`auxiliary_client.py:4529`, `agent_init.py:1088`, `error_classifier.py:736`…
Today a new model family must be taught to the codebase in a dozen places.

**Fold:** one `model_capabilities(model) -> ModelCaps` resolver (standardize on
the two best existing matchers: `reasoning_timeouts._match_any` longest-slug
regex + `coding_context._model_family`), rows declaring needles + capability
flags. **Migrate one consumer at a time behind existing helper names.**
**Risk: moderate-high** (precedence subtleties, e.g. `claude-opus-4` anchoring)
— highest correctness payoff of the folds.

### 1.6 Stop-guard/nudge injections → one `StopGuard` protocol

~10 "inject a synthetic turn to steer the loop" mechanisms exist; **three share
an essentially identical ~30-line injection contract** copied thrice in
`conversation_loop.py` (`:5244-5277` verify-on-stop, `:5311-5330` pre-verify,
`:5349-5377` kanban-stop): append attempted final_msg → synthetic `role:user`
nudge → bump counter → set finish_reason → flag `_*_synthetic` → `continue`.

**Fold:** `StopGuard(name, build_nudge, counter_attr, max_attempts,
finish_reason)` + one `_apply_stop_guard()` running the shared contract over an
ordered registry. Preserve per-guard budgets and the verify→pre_verify→kanban
order; the role-alternation invariants (`:5251-5264`, ticket #55733) live in
one place instead of three. **Risk: moderate.**

### 1.7 Context-file loaders → table-driven

`prompt_builder.py`: `_load_agents_md` (`:1888`) vs `_load_claude_md` (`:1907`)
are ~95% identical; `load_soul_md`/`_load_hermes_md`/`_load_cursorrules` share
the read → strip → threat-scan → `## header` wrap → truncate shape.
**Fold:** `ContextFileSpec(label, collect_fn, strip_frontmatter, header)` rows
+ one loader. Preserve first-match-wins ordering and exact `##` labels (model-
visible). **Risk: low.**

### 1.8 Per-platform send switch → capability table + adapter contract

`send_message_tool.py:779-1104` (325 lines, depth 12): six media arms with the
**same chunk-loop body** (`:894-906`, `:915-927`, `:931-943`, `:947-958`,
`:970-982`, `:1019-1031`), a caption-split preamble duplicated twice
(`:877-892` vs `:999-1018`), and an 11-arm text switch where six arms already
just call `_registry_standalone_send` and the `else` already calls the generic
`_send_via_adapter` (`:684-776` — the target abstraction, already written).
**Fold:** one `_send_chunked()` helper + widen the adapter `send()` contract to
carry media; Telegram/Matrix stay declared exceptions. **Risk: medium.**

### 1.9 Platform adapters: partial reuse of a rich base

`gateway/platforms/base.py` (5,650 lines) already centralizes chunking, media
extraction, debounce, retry — only `connect/disconnect/send` are abstract, and
chunking IS uniformly reused. But `_send_with_retry` (`base.py:4096`) is used
10× by feishu, 1× by telegram, and **0× by discord/slack/matrix** — discord
reimplements a whole rate-limit stack (`adapter.py:1554-1716`) because base
lacks a 429-classification hook. `send_multiple_images` is overridden in six
adapters.

**Fold:** (a) add a `_classify_send_error(exc) -> RetryDecision` hook so the
bespoke retry loops delete; (b) template-method the media senders
(`_send_media(kind, …)` + per-adapter `_upload` primitive), starting with
`send_document` (most uniform). **Risk: medium-high** per-kind; do
incrementally.

### 1.10 Small-helper unification (quick wins)

- **Truthy env parsing:** canonical `utils.is_truthy_value` exists, yet the
  literal set is re-inlined **9×** (`tool_guardrails.py:457`, `ssl_guard.py:25`,
  `chat_completion_helpers.py:529`, `auxiliary_client.py:548`,
  `shell_hooks.py:847`, `verification_stop.py:163`, `redact.py:68`,
  `image_routing.py:159`, inverse in `kanban_stop.py:32`).
- **Head/tail truncation with marker:** 3 full implementations
  (`prompt_builder.py:1791`, `moa_loop.py:389`, `context_compressor.py:435`)
  + 3 head-only variants → one `truncate_middle()` in `utils`.
- **Retry/backoff:** `agent/retry_utils.py` exists; **14 files** still
  hand-roll `for attempt … time.sleep` loops (several legitimately bespoke —
  migrate selectively).
- **Atomic writes:** `utils.atomic_json_write`/`atomic_replace` exist; 2
  holdouts re-implement tempfile+replace (`anthropic_adapter.py:1168-1187`,
  `secret_sources/bitwarden.py:246-257`).
- **Config access:** `cfg_get` exists (docstring: replaces a pattern appearing
  "50+ times") but **36 raw `.get().get()` chains** remain in
  gateway/+hermes_cli/, and the "env var OR config key" idiom is hand-written
  **44×** with *inconsistent precedence* → add `get_setting(config, *path,
  env=, default=)` and migrate site-by-site (each migration must confirm the
  prior precedence).
- **Plugin-category loaders:** `plugins/{cron_providers,memory,context_engine}/
  __init__.py` share up to 50 duplicate blocks — one generic category loader.
- **Per-tool schema/dispatch boilerplate:** `kanban_tools.py` shares 12-line
  blocks with 10+ tool files — a `tools/registry` helper for schema-declare +
  dispatch + error-wrap would thin every tool.

---

## 2. Security-relevant drift found by this survey (fix with the folds)

1. **camofox navigation lacks the secret-in-URL exfil guard** that
   `browser_navigate` enforces (`browser_tool.py:2705` vs
   `browser_camofox.py:492`). → closed by §1.3.
2. **Cron threat regexes never received the ReDoS bounded-filler fix**
   (`cronjob_tools.py:80` unbounded `(?:\w+\s+)*` vs `threat_patterns.py:59`).
   → closed by §1.2.
3. **Three independent child-env scrub policies** (`code_execution_tool.py:146`,
   `environments/local.py:156`, `browser_tool.py:90`) — each patchable
   independently, which is exactly how GHSA-rhgp-j443-p4rf class issues arise.
   `local.py`'s registry-derived blocklist is the natural single source; a
   `tools/tool_boundary.py` (`redact_output` / `child_env(purpose)` /
   `enforce_command_guard`) would make every tool declare its boundary instead
   of re-implementing it.

---

## 3. Never-nester decompositions (worst offenders, with the cure)

| Site | Now | Decomposition |
|---|---|---|
| `cli.py:8434 process_command` | depth **79**, 72 branches | §1.4 dispatch table; per-branch bodies → named methods with guard clauses |
| `agent/conversation_loop.py:523 run_conversation` | 4,939 lines, ~30 scattered `return {...}` exits, `compression_attempts` reset in ≥8 places | 3 steps in order: (1) single `_finalize_turn()` for all exits (mechanical); (2) extract inner retry-loop body (~3.5k lines) into a `TurnAttempt` object returning `{outcome: ok\|retry\|compress\|rotate\|abort}` that owns its counters; (3) strategy table on `error_classifier`'s `classified.reason` replacing the elif recovery cascade (`:2517-3121`) |
| `hermes_cli/main.py:12901 main` | 1,977 lines | NOT a ladder — argparse already dispatches via `set_defaults(func=…)`; 121 inline `add_parser/add_argument` calls just need moving into `build_<cmd>_parser()` modules — a pattern **already underway** (86 `build_*_parser` refs exist). Lowest-risk big win. |
| `hermes_cli/main.py:2789 select_provider_and_model` | depth 19, ~20-arm provider ladder (`:3116-3167`) | `PROVIDER_FLOWS: dict[str, Callable]` — the `_model_flow_*` functions already exist; plugins already auto-dispatch per the docstring |
| `tools/tts_tool.py:2284` | depth 16 via 11-arm provider elif + nested Edge `try/with/lambda` + triple-repeated opus conversion | provider table `{name: (import_fn, generate_fn, err)}` + extract `_resolve_tts_output_path`, `_run_edge_tts`, `_ensure_opus`; becomes a ~40-line orchestrator |
| `agent/agent_init.py:276 init_agent` | 1,867 lines, depth 14; **61 duplicate blocks vs run_agent.py** (extraction residue) | finish the extraction: phase functions (config, tools, memory, providers) + delete the residue |
| `tools/skills_tool.py:961 skill_view` | one giant `try:` pyramid | extract `_resolve_qualified_skill` / `_resolve_local_skill`, guard-clause early returns |
| `tools/terminal_tool.py:2826` | modal-arm ladder | per-backend dispatch table + `_check_modal_requirements` |

---

## 4. Prioritized plan

**Phase 1 — mechanical, low-risk, immediate (each independently shippable):**
1. §1.10 truthy/truncation/atomic-write/cfg_get adoptions (helpers all exist).
2. §1.2 canonical threat-pattern table (+ ReDoS drift fix).
3. §1.3 `browser_boundary.py` (+ camofox secret-guard fix).
4. `main()` subparser extraction (continues an in-progress pattern).
5. §1.7 context-file loader table.

**Phase 2 — structural folds, moderate risk:**
6. §1.1 `CapabilityRegistry[T]` (the flagship fold; tests pin behavior).
7. §1.4 `CommandDef.handler` dispatch (kills both ladders).
8. §1.6 `StopGuard` protocol.
9. §1.8 `_send_chunked` + adapter-contract widening.
10. `select_provider_and_model` → `PROVIDER_FLOWS`.
11. `tts_tool` provider table + extractions.

**Phase 3 — the big ones, high care:**
12. §3 `run_conversation` three-step split (finalize → TurnAttempt → strategy
    table). Highest value, hottest path; land each step separately with tests.
13. §1.5 model-capabilities table, one consumer at a time.
14. §1.9 adapter retry-hook, then media template-methods per-kind.
15. `init_agent` phase extraction + `agent_init↔run_agent` residue cleanup.

**Ground rules for all of it:** preserve public import paths (thin delegates),
land behind existing tests (install deps + run suite before each phase — this
environment currently has no pytest), one fold per PR, and treat the
prompt-visible strings (§1.7 headers, nudge texts) as behavior — byte-stable
unless intentionally changed.
