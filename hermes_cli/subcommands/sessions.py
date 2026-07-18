"""``hermes sessions`` subcommand parser + handler.

Extracted verbatim from ``hermes_cli/main.py:main()`` (god-file
follow-up). The large ``cmd_sessions`` handler is a closure exactly as
it was inline; all heavy imports (hermes_state, exporters) stay lazy
inside it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hermes_cli.config import get_hermes_home


def build_sessions_parser(subparsers) -> None:
    """Attach the ``sessions`` subcommand to ``subparsers``."""
    sessions_parser = subparsers.add_parser(
        "sessions",
        help="Manage session history (list, rename, export, prune, delete)",
        description="View and manage the SQLite session store",
    )
    sessions_subparsers = sessions_parser.add_subparsers(dest="sessions_action")

    sessions_list = sessions_subparsers.add_parser("list", help="List recent sessions")
    sessions_list.add_argument(
        "--source", help="Filter by source (cli, telegram, discord, etc.)"
    )
    sessions_list.add_argument(
        "--limit", type=int, default=20, help="Max sessions to show"
    )
    sessions_list.add_argument(
        "--workspace",
        metavar="NEEDLE",
        help="Only sessions in one workspace: a git repo root or project dir "
        "(matched by path substring or basename).",
    )

    def _add_session_filter_args(p, default_older_help):
        p.add_argument(
            "--older-than",
            metavar="AGE",
            help=default_older_help,
        )
        p.add_argument(
            "--newer-than",
            metavar="AGE",
            help="Only match sessions started within the last AGE "
            "(e.g. '5h', '2d') or after an ISO timestamp",
        )
        p.add_argument(
            "--before",
            metavar="TIME",
            help="Only match sessions started before TIME "
            "(duration ago like '5h', or ISO timestamp like '2026-07-05 14:30')",
        )
        p.add_argument(
            "--after",
            metavar="TIME",
            help="Only match sessions started at/after TIME "
            "(duration ago like '5h', or ISO timestamp)",
        )
        p.add_argument("--source", help="Only match sessions from this source")
        p.add_argument(
            "--title", help="Only match sessions whose title contains this substring"
        )
        p.add_argument(
            "--end-reason", help="Only match sessions with this end reason"
        )
        p.add_argument(
            "--cwd", help="Only match sessions whose working directory is under this path"
        )
        p.add_argument(
            "--min-messages", type=int, help="Only match sessions with >= N messages"
        )
        p.add_argument(
            "--max-messages", type=int, help="Only match sessions with <= N messages"
        )
        p.add_argument(
            "--model",
            help="Only match sessions whose model name contains this substring "
            "(e.g. 'sonnet', 'gpt-5', 'hermes')",
        )
        p.add_argument(
            "--provider",
            help="Only match sessions billed through this provider "
            "(e.g. openrouter, anthropic, nous)",
        )
        p.add_argument(
            "--user", help="Only match sessions from this user ID"
        )
        p.add_argument(
            "--chat-id", help="Only match sessions from this chat/channel ID"
        )
        p.add_argument(
            "--chat-type",
            help="Only match sessions with this chat type (e.g. dm, group)",
        )
        p.add_argument(
            "--branch",
            help="Only match sessions whose git branch contains this substring",
        )
        p.add_argument(
            "--min-tokens", type=int,
            help="Only match sessions with >= N total tokens (input+output)",
        )
        p.add_argument(
            "--max-tokens", type=int,
            help="Only match sessions with <= N total tokens (input+output)",
        )
        p.add_argument(
            "--min-cost", type=float,
            help="Only match sessions costing >= N USD (actual or estimated)",
        )
        p.add_argument(
            "--max-cost", type=float,
            help="Only match sessions costing <= N USD (actual or estimated)",
        )
        p.add_argument(
            "--min-tool-calls", type=int,
            help="Only match sessions with >= N tool calls",
        )
        p.add_argument(
            "--max-tool-calls", type=int,
            help="Only match sessions with <= N tool calls",
        )
        p.add_argument(
            "--dry-run",
            action="store_true",
            help="List matching sessions without changing anything",
        )
        p.add_argument(
            "--yes", "-y", action="store_true", help="Skip confirmation"
        )

    sessions_export = sessions_subparsers.add_parser(
        "export", help="Export sessions to JSONL, Markdown, or QMD"
    )
    sessions_export.add_argument(
        "output",
        nargs="?",
        help=(
            "Output path. JSONL: file path (use - for stdout, required). "
            "md/qmd: output directory (default: <hermes home>/session-exports)"
        ),
    )
    sessions_export.add_argument(
        "--format",
        choices=["jsonl", "md", "qmd", "html", "trace"],
        default="jsonl",
        help=(
            "Export format (default: jsonl). 'trace' emits Claude Code JSONL "
            "for the Hugging Face Agent Trace Viewer"
        ),
    )
    sessions_export.add_argument(
        "--upload",
        action="store_true",
        help=(
            "trace only: upload to your Hugging Face traces dataset instead "
            "of writing a local file (needs HF_TOKEN)"
        ),
    )
    sessions_export.add_argument(
        "--public",
        action="store_true",
        help="trace --upload only: create/update a public dataset instead of private",
    )
    sessions_export.add_argument(
        "--no-redact",
        action="store_true",
        help=(
            "trace only: skip the forced secret redaction; "
            "only use after manual review"
        ),
    )
    sessions_export.add_argument(
        "--only",
        choices=["user-prompts"],
        help=(
            "Export only a filtered view (user-prompts: one prompt record "
            "per line for jsonl, headed sections for md)"
        ),
    )
    sessions_export.add_argument(
        "--session-id", help="Session ID or unique prefix to export"
    )
    _add_session_filter_args(
        sessions_export,
        "Only export sessions older than AGE (duration like '5h'/'2d', "
        "bare number of days, or an ISO timestamp)",
    )
    sessions_export.add_argument(
        "--redact",
        action="store_true",
        help="Redact secrets (API keys, tokens, credentials) from exported content",
    )
    sessions_export.add_argument(
        "--lineage",
        choices=["single", "logical"],
        default="single",
        help="md/qmd only: export one row or its compression lineage",
    )
    sessions_export.add_argument(
        "--delete-after-verified",
        action="store_true",
        help="md/qmd only: after verified single-session export, delete that session (needs --yes)",
    )
    sessions_export.add_argument(
        "--force",
        action="store_true",
        help="md/qmd only: overwrite an existing export file",
    )

    sessions_delete = sessions_subparsers.add_parser(
        "delete", help="Delete a specific session"
    )
    sessions_delete.add_argument("session_id", help="Session ID to delete")
    sessions_delete.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )

    sessions_prune = sessions_subparsers.add_parser(
        "prune",
        help="Delete old sessions (filterable by time window, source, title, ...)",
    )
    _add_session_filter_args(
        sessions_prune,
        "Delete sessions older than AGE — days if bare number, or a duration "
        "like '5h'/'2d'/'1w', or an ISO timestamp (bare prune with no filters "
        "defaults to 90 days; any filter matches all ages)",
    )
    sessions_prune.add_argument(
        "--include-archived",
        action="store_true",
        help="Also delete archived sessions (excluded by default)",
    )

    sessions_archive = sessions_subparsers.add_parser(
        "archive",
        help="Bulk-archive (soft-hide) sessions matching filters — no deletion",
    )
    _add_session_filter_args(
        sessions_archive,
        "Only archive sessions older than AGE (duration like '5h'/'2d', "
        "bare number of days, or ISO timestamp)",
    )

    sessions_subparsers.add_parser(
        "optimize",
        help="Reclaim disk space: merge FTS5 segments + VACUUM (no data change)",
    )

    sessions_repair = sessions_subparsers.add_parser(
        "repair",
        help="Repair a malformed state.db schema so hidden sessions reappear",
        description=(
            "Recover a state.db whose schema is malformed (e.g. 'table "
            "messages_fts already exists'), which makes Desktop/Dashboard show "
            "no sessions. A backup is made first; sessions and messages are "
            "preserved and the FTS search index is rebuilt if needed."
        ),
    )
    sessions_repair.add_argument(
        "--check-only",
        action="store_true",
        help="Only report whether the database opens cleanly; do not modify it",
    )
    sessions_repair.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the timestamped backup copy (not recommended)",
    )

    sessions_subparsers.add_parser("stats", help="Show session store statistics")

    sessions_rename = sessions_subparsers.add_parser(
        "rename", help="Set or change a session's title"
    )
    sessions_rename.add_argument("session_id", help="Session ID to rename")
    sessions_rename.add_argument("title", nargs="+", help="New title for the session")

    sessions_browse = sessions_subparsers.add_parser(
        "browse",
        help="Interactive session picker — browse, search, and resume sessions",
    )
    sessions_browse.add_argument(
        "--source", help="Filter by source (cli, telegram, discord, etc.)"
    )
    sessions_browse.add_argument(
        "--limit", type=int, default=500, help="Max sessions to load (default: 500)"
    )

    def _confirm_prompt(prompt: str) -> bool:
        """Prompt for y/N confirmation, safe against non-TTY environments."""
        try:
            return input(prompt).strip().lower() in {"y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False

    def cmd_sessions(args):
        import json as _json

        # Shared display helpers still owned by main (other main-side
        # consumers exist). Lazy: main is fully imported before any
        # handler can run, so this cannot cycle.
        from hermes_cli.main import _relative_time, _session_browse_picker

        action = args.sessions_action

        # 'repair' must run BEFORE opening SessionDB(): a malformed schema is
        # exactly the case where SessionDB() can't open, so it operates on the
        # raw file path instead.
        if action == "repair":
            from hermes_state import (
                DEFAULT_DB_PATH,
                _db_opens_cleanly,
                repair_state_db_schema,
            )

            db_path = DEFAULT_DB_PATH
            if not db_path.exists():
                print(f"No session database at {db_path} (nothing to repair).")
                return
            reason = _db_opens_cleanly(db_path)
            if reason is None:
                print(f"✓ {db_path} opens cleanly — no repair needed.")
                return
            print(f"✗ {db_path} does not open cleanly: {reason}")
            if getattr(args, "check_only", False):
                return
            print("Repairing (a backup copy is made first)…")
            report = repair_state_db_schema(
                db_path, backup=not getattr(args, "no_backup", False)
            )
            if report.get("repaired"):
                if report.get("backup_path"):
                    print(f"  backup: {report['backup_path']}")
                print(f"  strategy: {report.get('strategy')}")
                try:
                    from hermes_state import SessionDB

                    n = SessionDB()._conn.execute(
                        "SELECT COUNT(*) FROM sessions"
                    ).fetchone()[0]
                    print(f"✓ Repaired — {n} sessions recovered.")
                except Exception:
                    print("✓ Repaired.")
            else:
                print(f"✗ Repair failed: {report.get('error')}")
                if report.get("backup_path"):
                    print(f"  A backup is preserved at: {report['backup_path']}")
                print("  Keep state.db and the backup; do not delete them.")
            return

        try:
            from hermes_state import SessionDB

            db = SessionDB()
        except Exception as e:
            print(f"Error: Could not open session database: {e}")
            return

        # Hide third-party tool sessions by default, but honour explicit --source
        _source = getattr(args, "source", None)
        _exclude = None if _source else ["tool"]

        if action == "list":
            from hermes_state import workspace_key as _ws_key

            sessions = db.list_sessions_rich(
                source=args.source, exclude_sources=_exclude, limit=args.limit
            )

            # Workspace filter: match a session by its workspace key (git repo
            # root, else cwd) — path substring or exact basename.
            _ws_filter = (getattr(args, "workspace", None) or "").strip()
            if _ws_filter:
                _needle = _ws_filter.lower()

                def _in_workspace(s):
                    key = (_ws_key(s) or "").lower()
                    return bool(key) and (
                        _needle in key or _needle == os.path.basename(key.rstrip("/\\"))
                    )

                sessions = [s for s in sessions if _in_workspace(s)]

            if not sessions:
                print("No sessions found.")
                return

            # Short workspace label: the repo/dir basename, "—" when unbound. The
            # Workspace column only appears once at least one session carries one
            # (or when filtering), so all-unbound listings read as before.
            def _ws_label(s):
                key = _ws_key(s)
                return (os.path.basename(key.rstrip("/\\")) or key) if key else "—"

            has_ws = bool(_ws_filter) or any(_ws_key(s) for s in sessions)
            has_titles = any(s.get("title") for s in sessions)

            if has_ws:
                if has_titles:
                    print(f"{'Title':<28} {'Workspace':<18} {'Last Active':<13} {'ID'}")
                    print("─" * 110)
                else:
                    print(f"{'Preview':<38} {'Workspace':<18} {'Last Active':<13} {'Src':<6} {'ID'}")
                    print("─" * 100)
                for s in sessions:
                    last_active = _relative_time(s.get("last_active"))
                    ws = _ws_label(s)[:16]
                    if has_titles:
                        title = (s.get("title") or "—")[:26]
                        print(f"{title:<28} {ws:<18} {last_active:<13} {s['id']}")
                    else:
                        preview = s.get("preview", "")[:36]
                        print(f"{preview:<38} {ws:<18} {last_active:<13} {s['source']:<6} {s['id']}")
                return

            if has_titles:
                print(f"{'Title':<32} {'Preview':<40} {'Last Active':<13} {'ID'}")
                print("─" * 110)
            else:
                print(f"{'Preview':<50} {'Last Active':<13} {'Src':<6} {'ID'}")
                print("─" * 95)
            for s in sessions:
                last_active = _relative_time(s.get("last_active"))
                preview = (
                    s.get("preview", "")[:38]
                    if has_titles
                    else s.get("preview", "")[:48]
                )
                if has_titles:
                    title = (s.get("title") or "—")[:30]
                    sid = s["id"]
                    print(f"{title:<32} {preview:<40} {last_active:<13} {sid}")
                else:
                    sid = s["id"]
                    print(f"{preview:<50} {last_active:<13} {s['source']:<6} {sid}")

        elif action == "export":
            from hermes_cli.session_filters import (
                build_prune_filters,
                describe_filters,
            )

            _filter_arg_names = (
                "older_than", "newer_than", "before", "after",
                "source", "title", "end_reason", "cwd",
                "min_messages", "max_messages", "model", "provider",
                "user", "chat_id", "chat_type", "branch",
                "min_tokens", "max_tokens", "min_cost", "max_cost",
                "min_tool_calls", "max_tool_calls",
            )
            _any_filters = any(
                getattr(args, a, None) is not None for a in _filter_arg_names
            )
            filters = None
            if _any_filters:
                try:
                    filters = build_prune_filters(args)
                except ValueError as e:
                    print(f"Error: {e}")
                    return
                # Unlike prune/archive, export includes archived sessions.
                filters["archived"] = None

            def _redact(data):
                if not args.redact or data is None:
                    return data
                from hermes_cli.session_export_md import redact_session_data

                return redact_session_data(data)

            def _collect_sessions():
                """Resolve --session-id / filters / bare export into a list
                of redacted session dicts, or None after printing an error."""
                if args.session_id:
                    resolved = db.resolve_session_id(args.session_id)
                    data = _redact(db.export_session(resolved)) if resolved else None
                    if not data:
                        print(f"Session '{args.session_id}' not found.")
                        return None
                    return [data]
                if filters:
                    candidates = db.list_prune_candidates(**filters)
                    if args.dry_run:
                        print(
                            f"Would export {len(candidates)} session(s) "
                            f"({describe_filters(filters)})."
                        )
                        for row in candidates[:100]:
                            print(f"  {row.get('id')}  {row.get('source', '')}")
                        if len(candidates) > 100:
                            print(f"  ... {len(candidates) - 100} more")
                        return None
                    return [
                        s
                        for s in (
                            _redact(db.export_session(row["id"])) for row in candidates
                        )
                        if s
                    ]
                if args.dry_run:
                    print("--dry-run requires at least one filter.")
                    return None
                return [_redact(s) for s in db.export_all(source=None)]

            # Prompt-only export (--only user-prompts): one prompt record per
            # line (jsonl) or headed sections (md). Delegates rendering to
            # hermes_cli.session_export.
            if getattr(args, "only", None):
                if args.format not in ("jsonl", "md"):
                    print("--only user-prompts supports --format jsonl or md.")
                    return
                from hermes_cli.session_export import (
                    export_record_count,
                    render_sessions_export,
                )

                sessions = _collect_sessions()
                if sessions is None:
                    db.close()
                    return
                rendered = render_sessions_export(
                    sessions,
                    fmt="markdown" if args.format == "md" else "jsonl",
                    only=args.only,
                )
                if not args.output or args.output == "-":
                    sys.stdout.write(rendered)
                    db.close()
                    return
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(rendered)
                count, noun = export_record_count(sessions, only=args.only)
                suffix = "" if count == 1 else "s"
                print(f"Exported {count} {noun}{suffix} to {args.output}")
                db.close()
                return

            # Standalone HTML export: one self-contained file (single session
            # or multi-session with sidebar navigation).
            if args.format == "html":
                if not args.output or args.output == "-":
                    print("HTML export requires an output file path.")
                    return
                from hermes_cli.session_export_html import (
                    generate_html_export,
                    generate_multi_session_html_export,
                )

                sessions = _collect_sessions()
                if sessions is None:
                    db.close()
                    return
                if len(sessions) == 1:
                    content = generate_html_export(sessions[0])
                else:
                    content = generate_multi_session_html_export(sessions)
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(content)
                suffix = "" if len(sessions) == 1 else "s"
                print(f"Exported {len(sessions)} session{suffix} to {args.output} (HTML)")
                db.close()
                return

            # Claude Code JSONL trace export — local file or HF upload.
            # Redaction is ON by default for traces (they leave the machine
            # when --upload is used); --no-redact opts out after review.
            if args.format == "trace":
                if getattr(args, "only", None):
                    print("--only user-prompts supports --format jsonl or md.")
                    db.close()
                    return
                session_id = args.session_id
                if not session_id and not filters:
                    # Match the shell's common intent: "the last thing I did".
                    rows = db.list_sessions_rich(limit=1, order_by_last_active=True)
                    session_id = rows[0].get("id") if rows else None
                    if not session_id:
                        print("No session found to export. Pass --session-id.")
                        db.close()
                        return
                if session_id and not db.resolve_session_id(session_id):
                    print(f"Session '{session_id}' not found.")
                    db.close()
                    return

                from agent.trace_upload import (
                    TraceRedactionError,
                    build_trace_jsonl,
                    upload_session_trace,
                )

                redact_trace = not getattr(args, "no_redact", False)

                if getattr(args, "upload", False):
                    if not session_id:
                        print("--upload exports one session: pass --session-id (or drop filters to use the most recent).")
                        db.close()
                        return
                    resolved = db.resolve_session_id(session_id)
                    db.close()
                    status = upload_session_trace(
                        resolved,
                        cwd="",
                        redact=redact_trace,
                        private=not getattr(args, "public", False),
                    )
                    print(status)
                    return

                # Local trace file(s)
                def _trace_ids():
                    if session_id:
                        return [db.resolve_session_id(session_id)]
                    candidates = db.list_prune_candidates(**filters)
                    if args.dry_run:
                        print(
                            f"Would export {len(candidates)} session(s) "
                            f"({describe_filters(filters)})."
                        )
                        for row in candidates[:100]:
                            print(f"  {row.get('id')}  {row.get('source', '')}")
                        if len(candidates) > 100:
                            print(f"  ... {len(candidates) - 100} more")
                        return None
                    return [row["id"] for row in candidates]

                ids = _trace_ids()
                if ids is None:
                    db.close()
                    return

                def _render_trace(sid):
                    meta = db.get_session(sid) or {}
                    messages = db.get_messages_as_conversation(sid)
                    if not messages:
                        return None
                    return build_trace_jsonl(
                        messages,
                        session_id=sid,
                        model=meta.get("model") or "",
                        cwd="",
                        redact=redact_trace,
                    )

                try:
                    if len(ids) == 1:
                        jsonl = _render_trace(ids[0])
                        if not jsonl:
                            print(f"No transcript to export for session '{ids[0]}'.")
                            db.close()
                            return
                        if not args.output or args.output == "-":
                            sys.stdout.write(jsonl)
                        else:
                            with open(args.output, "w", encoding="utf-8") as f:
                                f.write(jsonl)
                            print(f"Exported 1 session trace to {args.output}")
                    else:
                        out_dir = (
                            Path(args.output).expanduser()
                            if args.output and args.output != "-"
                            else get_hermes_home() / "session-exports"
                        )
                        out_dir.mkdir(parents=True, exist_ok=True)
                        exported = 0
                        for sid in ids:
                            jsonl = _render_trace(sid)
                            if not jsonl:
                                continue
                            (out_dir / f"{sid}.trace.jsonl").write_text(
                                jsonl, encoding="utf-8"
                            )
                            exported += 1
                        print(f"Exported {exported} session trace(s) to {out_dir}")
                except TraceRedactionError:
                    print("Redaction failed; refusing to export unredacted trace content.")
                db.close()
                return

            if args.format == "jsonl":
                if not args.output:
                    print("JSONL export requires an output path (use - for stdout).")
                    return
                if args.session_id:
                    resolved_session_id = db.resolve_session_id(args.session_id)
                    if not resolved_session_id:
                        print(f"Session '{args.session_id}' not found.")
                        return
                    data = _redact(db.export_session(resolved_session_id))
                    if not data:
                        print(f"Session '{args.session_id}' not found.")
                        return
                    line = _json.dumps(data, ensure_ascii=False) + "\n"
                    if args.output == "-":

                        sys.stdout.write(line)
                    else:
                        with open(args.output, "w", encoding="utf-8") as f:
                            f.write(line)
                        print(f"Exported 1 session to {args.output}")
                else:
                    if filters:
                        candidates = db.list_prune_candidates(**filters)
                        if args.dry_run:
                            print(
                                f"Would export {len(candidates)} session(s) "
                                f"({describe_filters(filters)})."
                            )
                            for row in candidates[:100]:
                                print(f"  {row.get('id')}  {row.get('source', '')}")
                            if len(candidates) > 100:
                                print(f"  ... {len(candidates) - 100} more")
                            return
                        sessions = [
                            s
                            for s in (
                                db.export_session(row["id"]) for row in candidates
                            )
                            if s
                        ]
                    else:
                        if args.dry_run:
                            print("--dry-run requires at least one filter.")
                            return
                        sessions = db.export_all(source=None)
                    if args.output == "-":

                        for s in sessions:
                            sys.stdout.write(
                                _json.dumps(_redact(s), ensure_ascii=False) + "\n"
                            )
                    else:
                        with open(args.output, "w", encoding="utf-8") as f:
                            for s in sessions:
                                f.write(
                                    _json.dumps(_redact(s), ensure_ascii=False) + "\n"
                                )
                        print(f"Exported {len(sessions)} sessions to {args.output}")
                return

            # Markdown / QMD export
            from hermes_cli.session_export_md import (
                append_manifest_entry,
                verify_export_file,
                write_session_markdown,
            )

            if args.output == "-":
                print("Markdown/QMD export writes files; stdout (-) is only supported with --format jsonl.")
                db.close()
                return
            output_dir = Path(args.output).expanduser() if args.output else get_hermes_home() / "session-exports"

            def _export_one(session_id: str):
                data = (
                    db.export_session_lineage(session_id)
                    if getattr(args, "lineage", "single") == "logical"
                    else db.export_session(session_id)
                )
                if not data:
                    return None, None
                data = _redact(data)
                path = write_session_markdown(
                    data,
                    output_dir,
                    fmt=args.format,
                    force=args.force,
                )
                append_manifest_entry(output_dir, data, path, fmt=args.format)
                return data, path

            if args.delete_after_verified and not args.yes:
                print("--delete-after-verified requires --yes.")
                db.close()
                return
            if args.delete_after_verified and not args.session_id:
                print("--delete-after-verified is only supported with --session-id.")
                db.close()
                return

            if args.session_id:
                resolved_session_id = db.resolve_session_id(args.session_id)
                if not resolved_session_id:
                    print(f"Session '{args.session_id}' not found.")
                    db.close()
                    return
                try:
                    data, exported_path = _export_one(resolved_session_id)
                except FileExistsError as e:
                    print(f"Export already exists: {e}. Pass --force to overwrite.")
                    db.close()
                    return
                if not data or not exported_path:
                    print(f"Session '{args.session_id}' not found.")
                    db.close()
                    return
                message_count = len(data.get("messages") or [])
                suffix = "" if message_count == 1 else "s"
                print(f"Exported 1 session ({message_count} message{suffix}) to {exported_path}")
                if args.delete_after_verified:
                    ok, reason = verify_export_file(exported_path, data)
                    if not ok:
                        print(f"Export verification failed; not deleting: {reason}")
                        db.close()
                        return
                    sessions_dir = get_hermes_home() / "sessions"
                    if db.delete_session(resolved_session_id, sessions_dir=sessions_dir):
                        print(f"Deleted exported session '{resolved_session_id}'.")
                    else:
                        print(f"Exported, but session '{resolved_session_id}' was not deleted because it was not found.")
                db.close()
                return

            if not filters:
                print(
                    "Refusing bulk export without a filter. Pass --session-id or "
                    "at least one filter (e.g. --older-than 90, --source telegram)."
                )
                db.close()
                return
            candidates = db.list_prune_candidates(**filters)
            if args.dry_run:
                print(
                    f"Would export {len(candidates)} session(s) "
                    f"({describe_filters(filters)})."
                )
                for row in candidates[:100]:
                    print(f"  {row.get('id')}  {row.get('source', '')}")
                if len(candidates) > 100:
                    print(f"  ... {len(candidates) - 100} more")
                db.close()
                return
            exported = 0
            for row in candidates:
                try:
                    data, exported_path = _export_one(row["id"])
                except FileExistsError as e:
                    print(f"Skipping existing export: {e}. Pass --force to overwrite.")
                    continue
                if data and exported_path:
                    exported += 1
            print(f"Exported {exported} session(s) to {output_dir}")

        elif action == "delete":
            resolved_session_id = db.resolve_session_id(args.session_id)
            if not resolved_session_id:
                print(f"Session '{args.session_id}' not found.")
                return
            if not args.yes:
                if not _confirm_prompt(
                    f"Delete session '{resolved_session_id}' and all its messages? [y/N] "
                ):
                    print("Cancelled.")
                    return
            sessions_dir = get_hermes_home() / "sessions"
            if db.delete_session(resolved_session_id, sessions_dir=sessions_dir):
                print(f"Deleted session '{resolved_session_id}'.")
            else:
                print(f"Session '{args.session_id}' not found.")

        elif action in ("prune", "archive"):
            from hermes_cli.session_filters import (
                build_prune_filters,
                describe_filters,
                format_epoch,
            )

            # Preserve the historical default ONLY for a truly bare
            # `hermes sessions prune`: no time window and no filters at all
            # means "older than 90 days". ANY filter — including --source —
            # suppresses the implicit cutoff, so `prune --source cron`
            # matches ALL cron sessions regardless of age. The preview +
            # confirmation below (count, oldest/newest) is the safety net.
            _non_time_filters = any(
                getattr(args, a, None) is not None
                for a in (
                    "source", "title", "end_reason", "cwd",
                    "min_messages", "max_messages", "model", "provider",
                    "user", "chat_id", "chat_type", "branch",
                    "min_tokens", "max_tokens", "min_cost", "max_cost",
                    "min_tool_calls", "max_tool_calls",
                )
            )
            if (
                action == "prune"
                and args.older_than is None
                and args.newer_than is None
                and args.before is None
                and args.after is None
                and not _non_time_filters
            ):
                args.older_than = "90"

            try:
                filters = build_prune_filters(args)
            except ValueError as e:
                print(f"Error: {e}")
                return

            if action == "archive" and not any(
                v for k, v in filters.items() if k != "older_than_days"
            ):
                print(
                    "Refusing to archive every ended session: pass at least one "
                    "filter (e.g. --newer-than 5h, --source cli, --title codex)."
                )
                return

            # Prune skips archived sessions unless --include-archived;
            # archive only targets not-yet-archived rows (idempotent).
            if action == "prune":
                filters["archived"] = (
                    None if getattr(args, "include_archived", False) else False
                )
            else:
                filters["archived"] = False

            candidates = db.list_prune_candidates(**filters)
            verb = "Delete" if action == "prune" else "Archive"
            if not candidates:
                print(f"No sessions match ({describe_filters(filters)}).")
                return

            # Candidates are ordered oldest-first — surface the age span so
            # the confirmation makes the blast radius obvious.
            _oldest = candidates[0].get("started_at")
            _newest = candidates[-1].get("started_at")
            _span = (
                f"oldest {format_epoch(_oldest)}, newest {format_epoch(_newest)}"
            )

            if args.dry_run or not args.yes:
                shown = candidates if args.dry_run else candidates[:15]
                print(
                    f"{len(candidates)} session(s) match "
                    f"({describe_filters(filters)}; {_span}):"
                )
                for s in shown:
                    title = (s.get("title") or "")[:36]
                    model = (s.get("model") or "-").split("/")[-1][:24]
                    print(
                        f"  {s['id']}  {format_epoch(s['started_at']):<17} "
                        f"{s['source']:<10} {model:<24} "
                        f"{s['message_count']:>4} msgs  {title}"
                    )
                if len(candidates) > len(shown):
                    print(f"  … and {len(candidates) - len(shown)} more")
                if args.dry_run:
                    print(f"Dry run — nothing {'deleted' if action == 'prune' else 'archived'}.")
                    return

            if not args.yes:
                if not _confirm_prompt(
                    f"{verb} these {len(candidates)} session(s) ({_span})? [y/N] "
                ):
                    print("Cancelled.")
                    return

            if action == "prune":
                sessions_dir = get_hermes_home() / "sessions"
                count = db.prune_sessions(sessions_dir=sessions_dir, **filters)
                print(f"Pruned {count} session(s).")
            else:
                count = db.archive_sessions(**filters)
                print(
                    f"Archived {count} session(s). They're hidden from listings "
                    "but fully recoverable (nothing was deleted)."
                )

        elif action == "rename":
            resolved_session_id = db.resolve_session_id(args.session_id)
            if not resolved_session_id:
                print(f"Session '{args.session_id}' not found.")
                return
            title = " ".join(args.title)
            try:
                if db.set_session_title(resolved_session_id, title):
                    print(f"Session '{resolved_session_id}' renamed to: {title}")
                else:
                    print(f"Session '{args.session_id}' not found.")
            except ValueError as e:
                print(f"Error: {e}")

        elif action == "browse":
            limit = getattr(args, "limit", 500) or 500
            source = getattr(args, "source", None)
            _browse_exclude = None if source else ["tool"]
            sessions = db.list_sessions_rich(
                source=source, exclude_sources=_browse_exclude, limit=limit
            )
            db.close()
            if not sessions:
                print("No sessions found.")
                return

            selected_id = _session_browse_picker(sessions)
            if not selected_id:
                print("Cancelled.")
                return

            # Launch hermes --resume <id> by replacing the current process
            print(f"Resuming session: {selected_id}")
            from hermes_cli.relaunch import relaunch

            relaunch(["--resume", selected_id])
            return  # won't reach here after execvp

        elif action == "optimize":
            db_path = db.db_path
            before_mb = (
                os.path.getsize(db_path) / (1024 * 1024)
                if db_path.exists()
                else 0.0
            )
            print("Optimizing session store (FTS merge + VACUUM)…")
            try:
                # vacuum() merges FTS5 segments (optimize_fts) then VACUUMs,
                # and returns the number of indexes it merged.
                n = db.vacuum()
            except Exception as e:
                print(f"Error: optimization failed: {e}")
                db.close()
                return
            after_mb = (
                os.path.getsize(db_path) / (1024 * 1024)
                if db_path.exists()
                else 0.0
            )
            saved = before_mb - after_mb
            print(f"Optimized {n} FTS index(es).")
            print(
                f"Database size: {before_mb:.1f} MB -> {after_mb:.1f} MB "
                f"(reclaimed {saved:.1f} MB)"
            )

        elif action == "stats":
            total = db.session_count()
            msgs = db.message_count()
            print(f"Total sessions: {total}")
            print(f"Total messages: {msgs}")
            for src in ["cli", "telegram", "discord", "whatsapp", "slack"]:
                c = db.session_count(source=src)
                if c > 0:
                    print(f"  {src}: {c} sessions")
            db_path = db.db_path
            if db_path.exists():
                size_mb = os.path.getsize(db_path) / (1024 * 1024)
                print(f"Database size: {size_mb:.1f} MB")

        else:
            sessions_parser.print_help()

        db.close()

    sessions_parser.set_defaults(func=cmd_sessions)
