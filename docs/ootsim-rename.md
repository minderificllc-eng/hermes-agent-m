# Project rename: Hermes Agent → OotSim (software) / Ooteo (agent)

**OotSim** = **Oot** **S**ynthetic **i**ntelligence **M**ind — the **software /
project**. **Ooteo** is the **agent** itself. Product, CLI, docs, and README use
OotSim; the agent's self-identity says "You are Ooteo…". Keep the two distinct.

This project began as a fork of [Nous Research's Hermes Agent](https://github.com/NousResearch/hermes-agent)
(MIT) and is being refactored toward a distinct goal: a synthetic intelligence
with a persistent **sense of self**. The rename is being rolled out in layers so
that existing installs keep working while the identity moves over.

## Done — identity & user-facing name (this pass)

- **Agent self-identity** (all five synced copies): `DEFAULT_AGENT_IDENTITY`
  (`agent/prompt_builder.py`), `DEFAULT_SOUL_MD` (`hermes_cli/default_soul.py`),
  `docker/SOUL.md`, `scripts/install.sh`, `scripts/install.ps1` — now the
  **Ooteo self-model statement** (*"You are Ooteo, a developing synthetic
  intelligence working to maintain a coherent, continuous, and revisable sense
  of self…"*). Kept byte-identical across all five.
- **Other agent self-references** also updated to Ooteo: the auxiliary
  replay-client fallback (`agent/auxiliary_client.py` → "You are Ooteo."), the
  CLI platform hint (`prompt_builder.py`), the kanban-worker line
  (`agent/kanban_stop.py`), and the curator role line (`agent/curator.py`). The
  `hermes_cli/doctor.py` fallback SOUL template now reuses `DEFAULT_SOUL_MD`
  instead of a hardcoded persona (removes a drift source).
- **README front door** → titled OotSim (the software), with a note that the
  runtime command and paths are unchanged for now.

### Attribution decision
The "created by Nous Research" line was removed from the *runtime identity
string* — Ooteo is its own named entity. This is a product/identity choice, not
a legal one: the MIT copyright notice in `LICENSE` is untouched (that is the
attribution the license actually requires). If a creator line is wanted in the
persona (e.g. "created by Minderific"), it's a one-line change in the five
synced copies above.

## Deliberately deferred (kept working as-is)

Per the chosen scope ("identity & docs only"), these mechanical identifiers were
**not** touched, because renaming them breaks existing installs, env, and
tooling without a migration:

| Surface | Left as | Blast radius if renamed |
|---|---|---|
| `HERMES_*` environment variables | unchanged | ~985 files; breaks every configured install |
| `~/.hermes` home directory | unchanged | ~582 files; orphans existing config/skills/memory |
| `hermes` CLI command | unchanged | user muscle memory + skills that shell out to `hermes` |
| `hermes-agent` package name (pyproject/setup/package.json) | unchanged | breaks `pip install hermes-agent[...]` |
| `hermes-agent.nousresearch.com` URLs & docs | unchanged | real, working endpoints; no OotSim site yet |
| `@hermes/ink`, internal module/package names | unchanged | large internal import graph |
| TUI banner art + tagline (`ui-tui`, `assets/banner.png`, `branding.tsx`) | unchanged | needs a branding decision (tagline, logo, keep ☤?) |
| Translated READMEs + `website/` docs tree | unchanged | large localization pass |

## When we do the deeper rename

A full rename should ship **with a migration**, not as a bare find-replace:

1. **Env vars:** read `OOTSIM_*` first, fall back to `HERMES_*` (back-compat
   shim), warn on the legacy name. Deprecate over time.
2. **Home dir:** prefer `~/.ootsim`, but auto-detect and migrate (or symlink)
   an existing `~/.hermes` on first run so no one loses skills/memory.
3. **CLI:** ship `ootsim` as the primary entry point with `hermes` as an alias
   during the transition.
4. **Package/URLs/site:** require an OotSim package name, docs site, and
   branding assets to exist first — otherwise we'd point users at dead links.

## Open branding inputs needed from the human

- Tagline (replacing "Messenger of the Digital Gods") and whether to keep the
  caduceus ☤ / commission new banner art.
- Creator/attribution line for the identity string, if any.
- Whether/when to stand up an `ootsim.*` docs site + package name (gates the URL
  and package rename).
