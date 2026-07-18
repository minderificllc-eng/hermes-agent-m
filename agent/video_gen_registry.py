"""
Video Generation Provider Registry
==================================

Central map of registered providers. Populated by plugins at import-time via
``PluginContext.register_video_gen_provider()``; consumed by the
``video_generate`` tool to dispatch each call to the active backend.

Active selection
----------------
The active provider is chosen by ``video_gen.provider`` in ``config.yaml``.
If unset, :func:`get_active_provider` applies fallback logic:

1. If exactly one *available* provider is registered, use it.
2. Otherwise return ``None`` (the tool surfaces a helpful error pointing
   the user at ``hermes tools``).

Mirrors ``agent/image_gen_registry.py`` so the two surfaces behave the
same: the unconfigured fallback is filtered by ``is_available()`` so a box
that has credentials for only one backend (e.g. DeepInfra, while the
``fal``/``xai`` plugins also register unconditionally) auto-selects it
instead of returning ``None``.

One deliberate difference from image gen: a configured-but-unregistered
``video_gen.provider`` **fails closed** (returns None) instead of falling
back — the tool then surfaces a "provider not registered" error rather
than silently running a different backend.

Implementation lives in :class:`agent.capability_registry.CapabilityRegistry`;
this module owns the instance, the config read, and the public surface.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from agent.capability_registry import CapabilityRegistry
from agent.video_gen_provider import VideoGenProvider

logger = logging.getLogger(__name__)

_REGISTRY: CapabilityRegistry[VideoGenProvider] = CapabilityRegistry(
    label="Video gen",
    provider_type=VideoGenProvider,
    logger=logger,
)

# Test-visible aliases: existing tests mutate these in place.
_providers = _REGISTRY._providers
_lock = _REGISTRY._lock


def register_provider(provider: VideoGenProvider) -> None:
    """Register a video generation provider.

    Re-registration (same ``name``) overwrites the previous entry and logs
    a debug message — this makes hot-reload scenarios (tests, dev loops)
    behave predictably.
    """
    _REGISTRY.register(provider)


def list_providers() -> List[VideoGenProvider]:
    """Return all registered providers, sorted by name."""
    return _REGISTRY.list_providers()


def get_provider(name: str) -> Optional[VideoGenProvider]:
    """Return the provider registered under *name*, or None."""
    return _REGISTRY.get_provider(name)


def get_active_provider() -> Optional[VideoGenProvider]:
    """Resolve the currently-active provider.

    Reads ``video_gen.provider`` from config.yaml; falls back per the
    module docstring.
    """
    configured: Optional[str] = None
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("video_gen") if isinstance(cfg, dict) else None
        if isinstance(section, dict):
            raw = section.get("provider")
            if isinstance(raw, str) and raw.strip():
                configured = raw.strip()
    except Exception as exc:
        logger.debug("Could not read video_gen.provider from config: %s", exc)

    return _REGISTRY.resolve_active(
        configured,
        configured_desc="video_gen.provider",
        fail_closed_on_missing_configured=True,
    )


def _reset_for_tests() -> None:
    """Clear the registry. **Test-only.**"""
    _REGISTRY.reset_for_tests()
