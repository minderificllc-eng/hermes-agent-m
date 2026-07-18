"""``hermes completion`` subcommand parser.

Extracted from ``hermes_cli/main.py:main()`` (god-file follow-up).
``cmd_completion`` needs the ROOT parser (it walks the argparse tree to
generate the script), so both the handler and the root parser are
injected.
"""

from __future__ import annotations

from typing import Callable


def build_completion_parser(subparsers, *, cmd_completion: Callable, root_parser) -> None:
    """Attach the ``completion`` subcommand to ``subparsers``."""
    completion_parser = subparsers.add_parser(
        "completion",
        help="Print shell completion script (bash, zsh, or fish)",
    )
    completion_parser.add_argument(
        "shell",
        nargs="?",
        default="bash",
        choices=["bash", "zsh", "fish"],
        help="Shell type (default: bash)",
    )
    completion_parser.set_defaults(func=lambda args: cmd_completion(args, root_parser))
