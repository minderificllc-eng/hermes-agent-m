"""Characterization tests for agent.model_capabilities.

model_capabilities() is a pure re-exposure of the pre-existing substring
predicates. These tests pin it EQUAL to those predicates across a broad model
matrix, so the consolidation can't drift from the behavior it replaced.
"""

import pytest

from agent.model_capabilities import ModelCaps, model_capabilities
from agent.prompt_builder import DEVELOPER_ROLE_MODELS, TOOL_USE_ENFORCEMENT_MODELS
from agent.coding_context import _model_family


MODELS = [
    "gpt-5", "gpt-4o", "o1-codex", "gemini-2.5-pro", "gemma-3-27b",
    "grok-4", "glm-4.6", "qwen3-coder", "deepseek-v3", "claude-opus-4-6",
    "claude-sonnet-4", "claude-3-5-haiku", "kimi-k2", "minimax-m2",
    "llama-4-scout", "mistral-large", "devstral", "", None, "some-unknown-model",
]


@pytest.mark.parametrize("model", MODELS)
def test_matches_existing_predicates(model):
    caps = model_capabilities(model)
    ml = (model or "").lower()
    assert caps.tool_use_enforcement == any(p in ml for p in TOOL_USE_ENFORCEMENT_MODELS)
    assert caps.developer_role == any(p in ml for p in DEVELOPER_ROLE_MODELS)
    assert caps.google_operational == ("gemini" in ml or "gemma" in ml)
    assert caps.openai_execution == ("gpt" in ml or "codex" in ml or "grok" in ml)
    assert caps.edit_format_family == _model_family(model)


def test_returns_frozen_modelcaps():
    caps = model_capabilities("gpt-5")
    assert isinstance(caps, ModelCaps)
    with pytest.raises(Exception):
        caps.developer_role = False  # frozen


def test_known_families_spot_check():
    # gpt-5: tool-use enforcement + developer role + openai execution + patch edits
    gpt5 = model_capabilities("gpt-5")
    assert gpt5.tool_use_enforcement and gpt5.developer_role and gpt5.openai_execution
    assert gpt5.edit_format_family == "patch"
    # claude: no tool-use enforcement, replace edits, no developer role
    claude = model_capabilities("claude-opus-4-6")
    assert not claude.tool_use_enforcement and not claude.developer_role
    assert claude.edit_format_family == "replace"
    # gemini: google operational + tool-use enforcement
    gem = model_capabilities("gemini-2.5-pro")
    assert gem.google_operational and gem.tool_use_enforcement
