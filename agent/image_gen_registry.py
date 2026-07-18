"""
Image Generation Provider Registry
==================================

Central map of registered providers. Populated by plugins at import-time via
``PluginContext.register_image_gen_provider()``; consumed by the
``image_generate`` tool to dispatch each call to the active backend.

Active selection
----------------
The active provider is chosen by ``image_gen.provider`` in ``config.yaml``.
If unset, :func:`get_active_provider` applies fallback logic:

1. If exactly one provider is registered, use it.
2. Otherwise if a provider named ``fal`` is registered, use it (legacy
   default — matches pre-plugin behavior).
3. Otherwise return ``None`` (the tool surfaces a helpful error pointing
   the user at ``hermes tools``).

Implementation lives in :class:`agent.capability_registry.CapabilityRegistry`;
this module owns the instance, the config read, and the public surface.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agent.capability_registry import CapabilityRegistry
from agent.image_gen_provider import ImageGenProvider

logger = logging.getLogger(__name__)

_REGISTRY: CapabilityRegistry[ImageGenProvider] = CapabilityRegistry(
    label="Image gen",
    provider_type=ImageGenProvider,
    logger=logger,
)

# Test-visible aliases: existing tests mutate these in place.
_providers = _REGISTRY._providers
_lock = _REGISTRY._lock


def register_provider(provider: ImageGenProvider) -> None:
    """Register an image generation provider.

    Re-registration (same ``name``) overwrites the previous entry and logs
    a debug message — this makes hot-reload scenarios (tests, dev loops)
    behave predictably.
    """
    _REGISTRY.register(provider)


def list_providers() -> List[ImageGenProvider]:
    """Return all registered providers, sorted by name."""
    return _REGISTRY.list_providers()


def get_provider(name: str) -> Optional[ImageGenProvider]:
    """Return the provider registered under *name*, or None."""
    return _REGISTRY.get_provider(name)


def get_active_provider() -> Optional[ImageGenProvider]:
    """Resolve the currently-active provider.

    Reads ``image_gen.provider`` from config.yaml; falls back per the
    module docstring.

    **Availability semantics** (mirrors :mod:`agent.web_search_registry`):

    - When ``image_gen.provider`` is explicitly set, the configured
      provider is returned even if :meth:`ImageGenProvider.is_available`
      reports False — the dispatcher surfaces a precise "X_API_KEY is not
      set" error rather than silently switching backends.
    - When ``image_gen.provider`` is unset, the fallback path (single-
      provider shortcut and the FAL legacy preference) is filtered by
      ``is_available()`` so we don't pick a provider the user has no
      credentials for.
    """
    configured: Optional[str] = None
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        if isinstance(section, dict):
            raw = section.get("provider")
            if isinstance(raw, str) and raw.strip():
                configured = raw.strip()
    except Exception as exc:
        logger.debug("Could not read image_gen.provider from config: %s", exc)

    return _REGISTRY.resolve_active(
        configured,
        configured_desc="image_gen.provider",
        legacy_preference=("fal",),
    )


def _reset_for_tests() -> None:
    """Clear the registry. **Test-only.**"""
    _REGISTRY.reset_for_tests()
