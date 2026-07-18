"""Tests for the _classify_send_error retry/backoff hook.

``BasePlatformAdapter._classify_send_error(exc) -> (retryable, retry_after)``
is the shared hook that lets every adapter's ``send()`` populate a failed
SendResult consistently: ``retryable`` drives ``_send_with_retry`` and
``retry_after`` overrides its backoff. The base default is the string-based
heuristic (behavior-preserving); Discord overrides it to surface the API's
authoritative Retry-After for structured 429s.
"""

from types import SimpleNamespace

import pytest

from gateway.platforms.base import BasePlatformAdapter


def _base_hook():
    """A minimal object bound to the base hook (avoids the ABC's abstract
    methods, which are irrelevant to error classification)."""
    obj = SimpleNamespace()
    obj._is_retryable_error = BasePlatformAdapter._is_retryable_error
    obj._classify_send_error = BasePlatformAdapter._classify_send_error.__get__(obj)
    return obj


def test_base_default_is_string_heuristic_no_retry_after():
    a = _base_hook()
    # A transient-looking error is retryable; no server retry-after by default.
    retryable, retry_after = a._classify_send_error(Exception("ConnectionResetError: reset by peer"))
    assert retryable is True
    assert retry_after is None
    # A non-transient error is not retryable.
    retryable2, _ = a._classify_send_error(Exception("permission denied"))
    assert retryable2 is False


def test_base_default_matches_is_retryable_error():
    """The hook's retryable verdict must equal the legacy string heuristic."""
    a = _base_hook()
    for msg in ("ConnectionResetError", "network is down", "totally fine", "bad request"):
        retryable, _ = a._classify_send_error(Exception(msg))
        assert retryable is BasePlatformAdapter._is_retryable_error(msg)


def test_discord_override_surfaces_server_retry_after():
    from plugins.platforms.discord.adapter import DiscordAdapter

    class _FakeRateLimit(Exception):
        # duck-typed 429 the detector recognizes (name + numeric retry_after)
        retry_after = 7.0

    _FakeRateLimit.__name__ = "RateLimitedError"
    # DiscordAdapter is concrete, so __new__ works and super() resolves.
    a = DiscordAdapter.__new__(DiscordAdapter)
    retryable, retry_after = a._classify_send_error(_FakeRateLimit())
    assert retryable is True
    assert retry_after == pytest.approx(7.0)


def test_discord_override_falls_back_to_base_for_non_429():
    from plugins.platforms.discord.adapter import DiscordAdapter

    a = DiscordAdapter.__new__(DiscordAdapter)
    # A plain non-rate-limit error routes through super(): string heuristic,
    # no server retry-after.
    retryable, retry_after = a._classify_send_error(Exception("ConnectionResetError: reset"))
    assert retryable is True
    assert retry_after is None
