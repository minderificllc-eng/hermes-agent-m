"""Tests for hermes_cli.config.get_setting — the env-var-or-config resolver."""

import pytest

from hermes_cli.config import get_setting


CFG = {"section": {"key": "cfg-value"}, "flag": {"on": False}}


def test_config_only_no_env(monkeypatch):
    monkeypatch.delenv("HERMES_X", raising=False)
    assert get_setting(CFG, "section", "key", env="HERMES_X", default="d") == "cfg-value"


def test_env_wins_by_default(monkeypatch):
    monkeypatch.setenv("HERMES_X", "env-value")
    assert get_setting(CFG, "section", "key", env="HERMES_X", default="d") == "env-value"


def test_env_wins_false_prefers_config(monkeypatch):
    monkeypatch.setenv("HERMES_X", "env-value")
    assert (
        get_setting(CFG, "section", "key", env="HERMES_X", default="d", env_wins=False)
        == "cfg-value"
    )


def test_env_wins_false_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("HERMES_X", "env-value")
    assert (
        get_setting(CFG, "missing", "key", env="HERMES_X", default="d", env_wins=False)
        == "env-value"
    )


def test_empty_env_is_treated_as_unset(monkeypatch):
    """An exported-but-blank env var must not shadow a real config value."""
    monkeypatch.setenv("HERMES_X", "")
    assert get_setting(CFG, "section", "key", env="HERMES_X", default="d") == "cfg-value"


def test_default_when_neither_source_has_it(monkeypatch):
    monkeypatch.delenv("HERMES_X", raising=False)
    assert get_setting(CFG, "nope", "key", env="HERMES_X", default="d") == "d"
    assert get_setting({}, "nope", env="HERMES_X", default=42) == 42


def test_falsy_config_value_is_preserved(monkeypatch):
    monkeypatch.delenv("HERMES_X", raising=False)
    # cfg has an explicit False — must be returned, not the default.
    assert get_setting(CFG, "flag", "on", env="HERMES_X", default=True) is False


def test_env_only_no_keys(monkeypatch):
    monkeypatch.setenv("HERMES_X", "just-env")
    assert get_setting(None, env="HERMES_X", default="d") == "just-env"
