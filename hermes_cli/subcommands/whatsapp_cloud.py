"""``hermes whatsapp-cloud`` subcommand parser.

Extracted from ``hermes_cli/main.py:main()`` (god-file follow-up).
Handler injected to avoid importing ``main``.
"""

from __future__ import annotations

from typing import Callable


def build_whatsapp_cloud_parser(subparsers, *, cmd_whatsapp_cloud: Callable) -> None:
    """Attach the ``whatsapp-cloud`` subcommand to ``subparsers``."""
    whatsapp_cloud_parser = subparsers.add_parser(
        "whatsapp-cloud",
        help="Set up WhatsApp Business Cloud API integration",
        description=(
            "Configure the official Meta WhatsApp Business Cloud API "
            "adapter (Business account required, public webhook URL "
            "required). Distinct from `hermes whatsapp` which sets up "
            "the Baileys bridge for personal accounts."
        ),
    )
    whatsapp_cloud_parser.set_defaults(func=cmd_whatsapp_cloud)
