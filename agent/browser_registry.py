"""
Browser Provider Registry
=========================

Central map of registered cloud browser providers. Populated by plugins at
import-time via :meth:`PluginContext.register_browser_provider`; consumed by
:func:`tools.browser_tool._get_cloud_provider` to route each cloud-mode
``browser_*`` tool call to the active backend.

Active selection
----------------
The active provider is chosen by configuration with this precedence:

1. ``browser.cloud_provider`` in ``config.yaml`` (explicit override).
2. Legacy preference order — ``browser-use`` → ``browserbase`` — filtered by
   availability. Matches the historic auto-detect order in
   :func:`tools.browser_tool._get_cloud_provider` (Browser Use checked first
   because it covers both the managed Nous gateway and direct API key path;
   Browserbase as the older direct-credentials fallback). ``firecrawl`` is
   intentionally NOT in the legacy walk — users only get Firecrawl as a
   cloud browser when they explicitly set ``browser.cloud_provider:
   firecrawl``, matching pre-migration behaviour where Firecrawl was never
   auto-selected.
3. Otherwise ``None`` — the dispatcher falls back to local browser mode.

The explicit-config branch (rule 1) intentionally ignores ``is_available()``
so the dispatcher surfaces a typed "X_API_KEY is not set" error to the user
instead of silently switching backends. Matches the legacy
:func:`tools.browser_tool._get_cloud_provider` behaviour for configured names.

There is intentionally NO "single-eligible shortcut" rule here (unlike
:mod:`agent.web_search_registry`). Pre-migration, the auto-detect branch in
``tools.browser_tool._get_cloud_provider`` only considered Browser Use and
Browserbase; Firecrawl was reachable only via an explicit
``browser.cloud_provider: firecrawl`` config key. Preserving that gate
matters because Firecrawl shares its API key with the *web* extract plugin
(``plugins/web/firecrawl/``), so users who set ``FIRECRAWL_API_KEY`` for web
extract must NOT get silently routed to a paid cloud browser on a fresh
install. Third-party browser-provider plugins added under
``~/.hermes/plugins/browser/<vendor>/`` are subject to the same gate — they
must be explicitly configured to take effect.

Note: there is no "capability" split here (unlike the web subsystem, which
has search/extract/crawl). Every browser provider implements the full
:class:`agent.browser_provider.BrowserProvider` lifecycle; the registry's
job is purely selection, not capability routing.

Implementation lives in :class:`agent.capability_registry.CapabilityRegistry`;
this module owns the instance, the legacy order, and the public surface.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agent.browser_provider import BrowserProvider
from agent.capability_registry import CapabilityRegistry

logger = logging.getLogger(__name__)

_REGISTRY: CapabilityRegistry[BrowserProvider] = CapabilityRegistry(
    label="Browser",
    provider_type=BrowserProvider,
    logger=logger,
    availability_warns=True,
)

# Test-visible aliases: existing tests mutate these in place.
_providers = _REGISTRY._providers
_lock = _REGISTRY._lock


# Legacy auto-detect order — used when no ``browser.cloud_provider`` is set.
# Matches the pre-migration walk in :func:`tools.browser_tool._get_cloud_provider`.
# Firecrawl is intentionally absent so users with ``FIRECRAWL_API_KEY`` set
# for web-extract don't get silently routed to a paid cloud browser. See
# the module docstring for the full rationale.
_LEGACY_PREFERENCE = (
    "browser-use",
    "browserbase",
)


def register_provider(provider: BrowserProvider) -> None:
    """Register a cloud browser provider.

    Re-registration (same ``name``) overwrites the previous entry and logs
    a debug message — makes hot-reload scenarios (tests, dev loops) behave
    predictably.
    """
    _REGISTRY.register(provider)


def list_providers() -> List[BrowserProvider]:
    """Return all registered providers, sorted by name."""
    return _REGISTRY.list_providers()


def get_provider(name: str) -> Optional[BrowserProvider]:
    """Return the provider registered under *name*, or None."""
    return _REGISTRY.get_provider(name)


def _resolve(configured: Optional[str]) -> Optional[BrowserProvider]:
    """Resolve the active browser provider.

    Resolution rules (in order):

    1. **Explicit "local".** Returns None — the dispatcher disables cloud
       mode entirely.
    2. **Explicit config wins, ignoring availability.**
    3. **Legacy preference walk, filtered by availability** — and no
       single-eligible shortcut. See the module docstring for both
       rationales.
    """
    return _REGISTRY.resolve_active(
        configured,
        configured_desc="browser cloud_provider",
        single_available_shortcut=False,
        legacy_preference=_LEGACY_PREFERENCE,
        local_sentinel="local",
    )


def _reset_for_tests() -> None:
    """Clear the registry. **Test-only.**"""
    _REGISTRY.reset_for_tests()
