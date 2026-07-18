"""
Web Search Provider Registry
============================

Central map of registered web providers. Populated by plugins at import-time
via :meth:`PluginContext.register_web_search_provider`; consumed by the
``web_search`` and ``web_extract`` tool wrappers in :mod:`tools.web_tools` to
dispatch each call to the active backend.

Active selection
----------------
The active provider is chosen by configuration with this precedence:

1. ``web.search_backend`` / ``web.extract_backend``
   (per-capability override).
2. ``web.backend`` (shared fallback).
3. If exactly one capability-eligible provider is registered AND available,
   use it.
4. Legacy preference order — ``firecrawl`` → ``parallel`` → ``tavily`` →
   ``exa`` → ``searxng`` → ``brave-free`` → ``ddgs`` — filtered by
   availability. Matches the historic ``tools.web_tools._get_backend()``
   candidate order so installs that never set a config key keep landing
   on the same provider they did before the plugin migration.
5. Otherwise ``None`` — the tool surfaces a helpful error pointing at
   ``hermes tools``.

The capability filter (``supports_search`` / ``supports_extract``) is
applied at every step so a search-only provider (``brave-free``)
configured as ``web.extract_backend`` correctly falls through to an
extract-capable backend.

Explicit config wins **ignoring availability**: a configured provider is
returned even if its :meth:`is_available` reports False, so the dispatcher
surfaces a precise "X_API_KEY is not set" error instead of silently routing
somewhere else. Matches legacy :func:`tools.web_tools._get_backend`
behavior for configured names.

Implementation lives in :class:`agent.capability_registry.CapabilityRegistry`;
this module owns the instance, the legacy order, the config reads, and the
public surface.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agent.capability_registry import CapabilityRegistry
from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_REGISTRY: CapabilityRegistry[WebSearchProvider] = CapabilityRegistry(
    label="Web",
    provider_type=WebSearchProvider,
    logger=logger,
)

# Test-visible aliases: existing tests mutate these in place.
_providers = _REGISTRY._providers
_lock = _REGISTRY._lock


def register_provider(provider: WebSearchProvider) -> None:
    """Register a web search/extract provider.

    Re-registration (same ``name``) overwrites the previous entry and logs
    a debug message — makes hot-reload scenarios (tests, dev loops) behave
    predictably.
    """
    _REGISTRY.register(provider)


def list_providers() -> List[WebSearchProvider]:
    """Return all registered providers, sorted by name."""
    return _REGISTRY.list_providers()


def get_provider(name: str) -> Optional[WebSearchProvider]:
    """Return the provider registered under *name*, or None."""
    return _REGISTRY.get_provider(name)


# ---------------------------------------------------------------------------
# Active-provider resolution
# ---------------------------------------------------------------------------


def _read_config_key(*path: str) -> Optional[str]:
    """Resolve a dotted config key from ``config.yaml``. Returns None on miss."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        cur = cfg
        for segment in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(segment)
        if isinstance(cur, str) and cur.strip():
            return cur.strip()
    except Exception as exc:
        logger.debug("Could not read config %s: %s", ".".join(path), exc)
    return None


# Legacy preference order — preserves behaviour for users who set no
# ``web.backend`` / ``web.<capability>_backend`` config key at all. Matches
# the historic candidate order in :func:`tools.web_tools._get_backend`
# (paid providers first so existing paid setups don't get downgraded to
# a free tier on upgrade). Filtered by ``is_available()`` at walk time so
# we don't surface a provider the user has no credentials for.
_LEGACY_PREFERENCE = (
    "firecrawl",
    "parallel",
    "tavily",
    "exa",
    "searxng",
    "brave-free",
    "ddgs",
)


def _resolve(configured: Optional[str], *, capability: str) -> Optional[WebSearchProvider]:
    """Resolve the active provider for a capability ("search" | "extract").

    Rules, in order: explicit config wins ignoring availability (a
    configured provider that doesn't support *capability* falls through),
    single capability-eligible + available provider shortcut, then the
    :data:`_LEGACY_PREFERENCE` walk filtered by capability + availability.
    See the module docstring for the full contract.
    """
    def _capable(p: WebSearchProvider) -> bool:
        if capability == "search":
            return bool(p.supports_search())
        if capability == "extract":
            return bool(p.supports_extract())
        return False

    return _REGISTRY.resolve_active(
        configured,
        configured_desc="web backend",
        capability_filter=_capable,
        legacy_preference=_LEGACY_PREFERENCE,
    )


def _disabled_web_plugin_for(configured: Optional[str] = None, *, capability: Optional[str] = None) -> Optional[str]:
    """Return the plugin key of a *disabled* bundled web plugin that would
    have provided the configured backend, or None.

    When a user sets ``web.extract_backend: firecrawl`` (or the search
    equivalent) but also lists ``web-firecrawl`` in ``plugins.disabled``,
    the provider never registers and the dispatcher would otherwise emit a
    misleading "No web extract provider configured. Set web.extract_backend
    to ..." error — even though the backend IS configured correctly. The
    real fix is to re-enable the plugin. This helper detects that case so
    the dispatcher can point the user at the actual cause (issue #40190
    follow-up: pi314's disabled-plugin symptom).

    Pass ``capability`` ("search" | "extract") to resolve the configured
    name straight from ``config.yaml`` (``web.<capability>_backend`` →
    ``web.backend``). This is more reliable than the resolved backend the
    dispatcher fell back to, since a disabled provider fails the
    ``_is_backend_available`` gate and the dispatcher silently drops to
    the shared default. An explicit ``configured`` name still wins when
    given.

    Matching is by convention: bundled web plugins live under the
    ``web/<vendor>`` key with the provider ``name`` differing only in
    hyphen/underscore (``brave-free`` provider ⇄ ``web/brave_free`` key,
    ``firecrawl`` ⇄ ``web/firecrawl``). We normalize both sides before
    comparing so every bundled provider is covered without hardcoding a
    per-vendor table.
    """
    def _norm(s: str) -> str:
        return s.strip().lower().replace("-", "_")

    if not configured and capability in ("search", "extract"):
        configured = (
            _read_config_key("web", f"{capability}_backend")
            or _read_config_key("web", "backend")
        )
    if not configured:
        return None

    want = _norm(configured)
    try:
        from hermes_cli.plugins import get_plugin_manager

        pm = get_plugin_manager()
        for key, loaded in pm._plugins.items():
            if not isinstance(key, str) or not key.startswith("web/"):
                continue
            if loaded.enabled:
                continue
            if loaded.error != "disabled via config":
                continue
            vendor = key.split("/", 1)[1]
            if _norm(vendor) == want:
                return key
    except Exception as exc:  # noqa: BLE001 — diagnostics are best-effort
        logger.debug("disabled-web-plugin lookup failed: %s", exc)
    return None


def get_active_search_provider() -> Optional[WebSearchProvider]:
    """Resolve the currently-active web search provider.

    Reads ``web.search_backend`` (preferred) or ``web.backend`` (shared
    fallback) from config.yaml; falls back per the module docstring.
    """
    explicit = _read_config_key("web", "search_backend") or _read_config_key("web", "backend")
    return _resolve(explicit, capability="search")


def get_active_extract_provider() -> Optional[WebSearchProvider]:
    """Resolve the currently-active web extract provider.

    Reads ``web.extract_backend`` (preferred) or ``web.backend`` (shared
    fallback) from config.yaml; falls back per the module docstring.
    """
    explicit = _read_config_key("web", "extract_backend") or _read_config_key("web", "backend")
    return _resolve(explicit, capability="extract")


def _reset_for_tests() -> None:
    """Clear the registry. **Test-only.**"""
    _REGISTRY.reset_for_tests()
