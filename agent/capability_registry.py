"""
Generic capability-provider registry
====================================

One implementation of the registry pattern shared by the six capability
subsystems (TTS, transcription, image gen, video gen, web search/extract,
cloud browser). Before this fold each ``agent/<capability>_registry.py``
carried its own ~90%-identical copy of: a ``_providers`` dict + lock, the
``register_provider`` gate (isinstance → name check → overwrite + log),
``list_providers`` / ``get_provider`` / ``_reset_for_tests``, the
``_is_available_safe`` wrapper, and the active-provider resolution pipeline
(explicit-config-wins → single-available shortcut → legacy-preference walk).

The per-capability modules remain the public import surface — they own
their instance, their docstring (the behavioral contract), their constants
(``_BUILTIN_NAMES``, ``_LEGACY_PREFERENCE``) and their module logger (test
``caplog`` filters key on the module logger name). They alias
``_providers``/``_lock`` to the instance's objects so existing tests that
mutate the dict in place keep working.

Genuine per-capability differences are knobs, not copies:

- ``normalize_keys``      — TTS/transcription lowercase+strip names.
- ``builtin_names``       — TTS/transcription reject built-in shadows.
- ``capability_filter``   — web routes by supports_search/supports_extract.
- ``fail_closed_on_missing_configured`` — video gen returns None when the
  configured name is unregistered (others fall through to auto-detect).
- ``single_available_shortcut`` — browser deliberately has NO
  single-provider shortcut (Firecrawl auto-select gate; see its module
  docstring).
- ``local_sentinel``      — browser's explicit ``local`` disables cloud.
- ``availability_warns``  — browser logs is_available() failures at
  WARNING with traceback; others at DEBUG.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Generic, List, Optional, Sequence, TypeVar

T = TypeVar("T")


class CapabilityRegistry(Generic[T]):
    """Thread-safe name → provider map with shared resolution rules."""

    def __init__(
        self,
        *,
        label: str,
        provider_type: type,
        logger: logging.Logger,
        normalize_keys: bool = False,
        builtin_names: frozenset = frozenset(),
        builtin_label: Optional[str] = None,
        availability_warns: bool = False,
    ) -> None:
        self.label = label
        self.provider_type = provider_type
        self.logger = logger
        self.normalize_keys = normalize_keys
        self.builtin_names = builtin_names
        # Some subsystems brand their built-ins differently from the
        # provider label (transcription providers, "Built-in STT providers").
        self.builtin_label = builtin_label or label
        self.availability_warns = availability_warns
        self._providers: Dict[str, T] = {}
        self._lock = threading.Lock()

    # -- registration -----------------------------------------------------

    def register(self, provider: T) -> None:
        """Register a provider.

        Rejects non-``provider_type`` instances (TypeError) and empty
        ``.name`` (ValueError). When ``builtin_names`` is set, a name
        colliding with a built-in logs a warning and is ignored
        (built-ins-always-win). Re-registration overwrites and logs at
        debug — makes hot-reload scenarios behave predictably.
        """
        if not isinstance(provider, self.provider_type):
            type_name = self.provider_type.__name__
            article = "an" if type_name[0].upper() in "AEIOU" else "a"
            raise TypeError(
                f"register_provider() expects {article} {type_name} instance, "
                f"got {type(provider).__name__}"
            )
        name = provider.name  # type: ignore[attr-defined]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{self.label} provider .name must be a non-empty string")
        key = name.strip().lower() if self.normalize_keys else name
        if self.builtin_names and key in self.builtin_names:
            self.logger.warning(
                "%s provider '%s' shadows a built-in name; registration ignored. "
                "Built-in %s providers (%s) always win — pick a different name.",
                self.label, key, self.builtin_label, ", ".join(sorted(self.builtin_names)),
            )
            return
        with self._lock:
            existing = self._providers.get(key)
            self._providers[key] = provider
        if existing is not None:
            self.logger.debug(
                "%s provider '%s' re-registered (was %r)",
                self.label, key, type(existing).__name__,
            )
        else:
            self.logger.debug(
                "Registered %s provider '%s' (%s)",
                self.label, key, type(provider).__name__,
            )

    # -- lookup -----------------------------------------------------------

    def list_providers(self) -> List[T]:
        """All registered providers, sorted by name."""
        with self._lock:
            items = list(self._providers.values())
        return sorted(items, key=lambda p: p.name)  # type: ignore[attr-defined]

    def get_provider(self, name: str) -> Optional[T]:
        """Provider registered under *name*, or None."""
        if not isinstance(name, str):
            return None
        key = name.strip().lower() if self.normalize_keys else name.strip()
        with self._lock:
            return self._providers.get(key)

    def snapshot(self) -> Dict[str, T]:
        with self._lock:
            return dict(self._providers)

    # -- resolution -------------------------------------------------------

    def is_available_safe(self, provider: T) -> bool:
        """Wrap ``is_available()`` so a buggy provider doesn't kill resolution."""
        try:
            return bool(provider.is_available())  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            if self.availability_warns:
                self.logger.warning(
                    "%s provider %s.is_available() raised %s — treating as unavailable",
                    self.label, provider.name, exc, exc_info=True,  # type: ignore[attr-defined]
                )
            else:
                self.logger.debug(
                    "%s provider %s.is_available() raised %s",
                    self.label, provider.name, exc,  # type: ignore[attr-defined]
                )
            return False

    def resolve_active(
        self,
        configured: Optional[str],
        *,
        configured_desc: str,
        capability_filter: Optional[Callable[[T], bool]] = None,
        fail_closed_on_missing_configured: bool = False,
        single_available_shortcut: bool = True,
        legacy_preference: Sequence[str] = (),
        local_sentinel: Optional[str] = None,
    ) -> Optional[T]:
        """Shared active-provider resolution pipeline.

        1. ``local_sentinel`` short-circuit (browser's explicit ``local``).
        2. **Explicit config wins, ignoring availability** — the dispatcher
           surfaces a precise "X_API_KEY is not set" error instead of a
           silent backend switch. A configured-but-unregistered name either
           falls through (default) or fails closed
           (``fail_closed_on_missing_configured``). A configured name that
           fails ``capability_filter`` always falls through.
        3. **Single-available shortcut** — when exactly one registered
           provider passes the capability filter AND ``is_available()``.
        4. **Legacy preference walk**, filtered by capability +
           availability, preserving each subsystem's pre-plugin-migration
           default selection.
        """
        snapshot = self.snapshot()
        capable = capability_filter or (lambda p: True)

        if local_sentinel is not None and configured == local_sentinel:
            return None

        if configured:
            provider = snapshot.get(configured)
            if provider is not None and capable(provider):
                return provider
            if provider is None:
                self.logger.debug(
                    "%s '%s' configured but not registered; %s",
                    configured_desc, configured,
                    "failing closed" if fail_closed_on_missing_configured
                    else "falling back",
                )
                if fail_closed_on_missing_configured:
                    return None
            else:
                self.logger.debug(
                    "%s '%s' configured but does not support the requested "
                    "capability; falling back",
                    configured_desc, configured,
                )

        if single_available_shortcut:
            eligible = [
                p for p in snapshot.values()
                if capable(p) and self.is_available_safe(p)
            ]
            if len(eligible) == 1:
                return eligible[0]

        for legacy in legacy_preference:
            provider = snapshot.get(legacy)
            if provider is not None and capable(provider) and self.is_available_safe(provider):
                return provider

        return None

    # -- test support -----------------------------------------------------

    def reset_for_tests(self) -> None:
        """Clear the registry. **Test-only.**"""
        with self._lock:
            self._providers.clear()
