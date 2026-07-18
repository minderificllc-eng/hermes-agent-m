"""``hermes secrets`` subcommand parser.

Extracted from ``hermes_cli/main.py:main()`` (god-file follow-up).
The Bitwarden/1Password CLI registrars are lazily imported at build
time, matching the import cost of the original inline block.
"""

from __future__ import annotations


def build_secrets_parser(subparsers) -> None:
    """Attach the ``secrets`` subcommand to ``subparsers``."""
    secrets_parser = subparsers.add_parser(
        "secrets",
        help="Manage external secret sources (Bitwarden, 1Password)",
        description=(
            "Pull API keys from an external secret manager at process startup "
            "instead of storing them in ~/.hermes/.env.  Supports Bitwarden "
            "Secrets Manager and 1Password.  See: "
            "https://hermes-agent.nousresearch.com/docs/user-guide/secrets/"
        ),
    )
    secrets_subparsers = secrets_parser.add_subparsers(dest="secrets_command")

    secrets_bw = secrets_subparsers.add_parser(
        "bitwarden",
        aliases=["bw"],
        help="Bitwarden Secrets Manager integration",
    )

    secrets_op = secrets_subparsers.add_parser(
        "onepassword",
        aliases=["op", "1password"],
        help="1Password (op:// references) integration",
    )

    # Lazy import — only pays for itself when this subcommand is actually used.
    from hermes_cli import secrets_cli as _secrets_cli
    from hermes_cli import onepassword_secrets_cli as _op_secrets_cli

    _secrets_cli.register_cli(secrets_bw)
    _op_secrets_cli.register_cli(secrets_op)

    def _dispatch_secrets(args):  # noqa: ANN001
        sub = getattr(args, "secrets_command", None)
        bw_sub = getattr(args, "secrets_bw_command", None)
        op_sub = getattr(args, "secrets_op_command", None)
        if sub in ("bitwarden", "bw") and bw_sub is not None:
            return args.func(args)
        if sub in ("onepassword", "op", "1password") and op_sub is not None:
            return args.func(args)
        secrets_parser.print_help()
        return 0

    secrets_parser.set_defaults(func=_dispatch_secrets)
