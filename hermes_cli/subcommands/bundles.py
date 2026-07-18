"""``hermes bundles`` subcommand parser.

Extracted from ``hermes_cli/main.py:main()`` (god-file follow-up).
The bundles CLI registrar is lazily imported at build time, matching
the import cost of the original inline block.
"""

from __future__ import annotations


def build_bundles_parser(subparsers) -> None:
    """Attach the ``bundles`` subcommand to ``subparsers``."""
    bundles_parser = subparsers.add_parser(
        "bundles",
        help="Create, list, and manage skill bundles (aliases for multiple skills)",
        description=(
            "Skill bundles let you load several skills under one slash "
            "command. `/<bundle>` from the CLI or gateway loads every "
            "referenced skill at once."
        ),
    )
    from hermes_cli.bundles import register_cli as _bundles_register, bundles_command
    _bundles_register(bundles_parser)
    bundles_parser.set_defaults(func=bundles_command)
