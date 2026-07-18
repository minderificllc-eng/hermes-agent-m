"""Prompt-side model-family capabilities — one query API.

A model's *prompt-shaping* family (does it need tool-use enforcement, the
developer role, Google/OpenAI operational guidance, and which edit format it
was trained on) was answered by substring checks scattered across
``system_prompt.py``, ``prompt_builder`` tuples, ``chat_completions.py`` and
``coding_context._model_family``. This module gives those one resolver so a
new model family is taught its prompt guidance in one place.

SCOPE — prompt shaping ONLY. This intentionally does NOT cover the
*wire-format / cache-envelope / header-route* checks (the bare ``"claude" in
model`` tests in ``agent_runtime_helpers``, ``agent_init``,
``anthropic_adapter`` …). Those are context-specific by design —
``agent_runtime_helpers`` deliberately splits ``is_claude`` from
``is_anthropic_wire`` because Kimi/Moonshot on OpenRouter use Claude's
cache_control envelope without being Claude — and folding them into a single
``is_anthropic_model()`` silently serves 0% cache hits and re-bills every
turn. See docs/refactoring-opportunities.md §1.5.

Behavior is a pure re-exposure of the existing substring predicates,
characterization-pinned in ``tests/agent/test_model_capabilities.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelCaps:
    """Prompt-shaping capability flags for a model id."""

    tool_use_enforcement: bool      # inject TOOL_USE_ENFORCEMENT_GUIDANCE
    developer_role: bool            # swap system->developer role at the API boundary
    google_operational: bool        # inject GOOGLE_MODEL_OPERATIONAL_GUIDANCE
    openai_execution: bool          # inject OPENAI_MODEL_EXECUTION_GUIDANCE
    edit_format_family: Optional[str]  # "patch" | "replace" | None


def model_capabilities(model: Optional[str]) -> ModelCaps:
    """Resolve the prompt-shaping capability flags for *model*.

    Imports are deferred to avoid an import cycle with the prompt-assembly
    modules that consume this resolver.
    """
    from agent.prompt_builder import (
        DEVELOPER_ROLE_MODELS,
        TOOL_USE_ENFORCEMENT_MODELS,
    )
    from agent.coding_context import _model_family

    ml = (model or "").lower()
    return ModelCaps(
        tool_use_enforcement=any(p in ml for p in TOOL_USE_ENFORCEMENT_MODELS),
        developer_role=any(p in ml for p in DEVELOPER_ROLE_MODELS),
        # Mirrors system_prompt.py's inline branches exactly.
        google_operational=("gemini" in ml or "gemma" in ml),
        openai_execution=("gpt" in ml or "codex" in ml or "grok" in ml),
        edit_format_family=_model_family(model),
    )
