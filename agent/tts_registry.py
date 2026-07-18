"""
TTS Provider Registry
=====================

Central map of registered TTS providers. Populated by plugins at
import-time via :meth:`PluginContext.register_tts_provider`; consumed
by :mod:`tools.tts_tool` to dispatch ``text_to_speech`` tool calls to
the active plugin backend **when** the configured ``tts.provider``
name is neither a built-in nor a command-type provider.

Built-ins-always-win
--------------------
Plugin names that collide with a built-in TTS provider (``edge``,
``openai``, ``elevenlabs``, ``minimax``, ``gemini``, ``mistral``,
``xai``, ``piper``, ``kittentts``, ``neutts``) are rejected at
registration with a warning. This invariant is also re-checked at
dispatch time in :func:`tools.tts_tool._dispatch_to_plugin_provider`.

Command-providers-win-over-plugins
----------------------------------
This registry doesn't enforce the command-vs-plugin precedence — that
lives in the dispatcher, which checks for a same-name
``tts.providers.<name>: type: command`` entry before consulting the
registry. The rationale is locality: a name declared in the user's
``config.yaml`` is more specific to their setup than a plugin that
happens to be installed.

Implementation lives in :class:`agent.capability_registry.CapabilityRegistry`;
this module owns the instance, the built-in name set, and the public
surface.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agent.capability_registry import CapabilityRegistry
from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)


# Names reserved for native built-in TTS handlers. Plugins cannot
# register a name in this set — the registration call is rejected with
# a warning. **Kept in sync with ``BUILTIN_TTS_PROVIDERS`` in
# :mod:`tools.tts_tool`** — a regression test in
# ``tests/agent/test_tts_registry.py::TestBuiltinSync`` fails if the
# two lists drift. Importing from ``tools.tts_tool`` directly would
# create a circular dependency (``tools.tts_tool`` imports
# ``agent.tts_registry`` for dispatch).
_BUILTIN_NAMES = frozenset({
    "edge",
    "elevenlabs",
    "openai",
    "minimax",
    "xai",
    "mistral",
    "gemini",
    "neutts",
    "kittentts",
    "piper",
    "deepinfra",
})

_REGISTRY: CapabilityRegistry[TTSProvider] = CapabilityRegistry(
    label="TTS",
    provider_type=TTSProvider,
    logger=logger,
    normalize_keys=True,
    builtin_names=_BUILTIN_NAMES,
)

# Test-visible aliases: existing tests mutate these in place.
_providers = _REGISTRY._providers
_lock = _REGISTRY._lock


def register_provider(provider: TTSProvider) -> None:
    """Register a TTS provider.

    Rejects:

    - Non-:class:`TTSProvider` instances (raises :class:`TypeError`).
    - Empty/whitespace ``.name`` (raises :class:`ValueError`).
    - Names colliding with a built-in (logs a warning, silently
      ignores — built-ins-always-win invariant).

    Re-registration (same ``name``) overwrites the previous entry and
    logs a debug message — makes hot-reload scenarios (tests, dev
    loops) behave predictably.
    """
    _REGISTRY.register(provider)


def list_providers() -> List[TTSProvider]:
    """Return all registered providers, sorted by name."""
    return _REGISTRY.list_providers()


def get_provider(name: str) -> Optional[TTSProvider]:
    """Return the provider registered under *name*, or None.

    Name matching is case-insensitive and whitespace-tolerant — mirrors
    how ``tools.tts_tool._get_provider`` normalizes the configured
    ``tts.provider`` value.
    """
    return _REGISTRY.get_provider(name)


def _reset_for_tests() -> None:
    """Clear the registry. **Test-only.**"""
    _REGISTRY.reset_for_tests()
