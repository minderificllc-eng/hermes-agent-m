"""Characterization tests for the process_command slash-dispatch tables.

process_command was a 71-branch ``elif canonical ==`` ladder (663 lines,
AST nesting depth 79 — the worst function in the codebase). It is now a
43-line, depth-1 dispatch over two tables built by
``HermesCLI._slash_command_tables``:

- ``returning`` — canonical -> ``_cmd_<name>`` method NAME; the method
  returns the exact process_command result (quit -> False, undo-invalid
  -> None which the caller treats as "exit REPL", cancels -> True). Stored
  by name and resolved via ``getattr`` at dispatch so partial test stubs
  only need the one handler they exercise.
- ``delegates`` — canonical -> lambda that runs a handler for effect and
  falls through to the shared ``return True``.

These tests pin the tables so a command dropped from a table (or a typo in
a handler name) fails loudly instead of silently becoming an "unknown
command" at the REPL.
"""

from __future__ import annotations

from cli import HermesCLI


def _tables():
    inst = HermesCLI.__new__(HermesCLI)
    return HermesCLI._slash_command_tables(inst)


def test_returning_handler_names_resolve_on_the_class():
    """Every returning entry names a real ``_cmd_*`` method (no typos)."""
    returning, _ = _tables()
    missing = [name for name in returning.values() if not hasattr(HermesCLI, name)]
    assert not missing, f"returning handlers name non-existent methods: {missing}"


def test_tables_are_disjoint():
    """A canonical command routes through exactly one table."""
    returning, delegates = _tables()
    overlap = set(returning) & set(delegates)
    assert not overlap, f"commands in both tables: {sorted(overlap)}"


def test_expected_commands_are_covered():
    """Regression snapshot: the exact command set process_command dispatches.

    If a command is intentionally added/removed, update this set — the point
    is that the change is deliberate and reviewed, not a silent drop that
    routes a real command into the unknown-command fallback.
    """
    returning, delegates = _tables()
    covered = set(returning) | set(delegates)
    expected = {
        # returning (propagate the process_command result)
        "quit", "exit", "redraw", "clear", "title", "handoff", "new", "retry",
        "undo", "skills", "statusbar", "update", "version", "reload",
        "reload-skills", "plugins", "queue", "steer", "moa",
        # delegates (run for effect, continue the REPL)
        "help", "profile", "tools", "toolsets", "config", "history", "resume",
        "sessions", "model", "codex-runtime", "personality", "pet", "hatch",
        "prompt", "branch", "save", "cron", "suggestions", "blueprint",
        "curator", "kanban", "learn", "memory", "platforms", "status",
        "timestamps", "verbose", "footer", "yolo", "reasoning", "fast",
        "compress", "usage", "credits", "billing", "insights", "copy", "debug",
        "paste", "image", "reload-mcp", "bundles", "browser", "rollback",
        "snapshot", "stop", "agents", "journey", "background", "goal",
        "subgoal", "skin", "voice", "busy",
    }
    assert covered == expected, (
        f"table coverage drifted.\n"
        f"  dropped: {sorted(expected - covered)}\n"
        f"  added:   {sorted(covered - expected)}"
    )


def test_delegate_dispatch_routes_to_handler(monkeypatch):
    """A delegate command invokes its handler and keeps the REPL alive."""
    inst = HermesCLI.__new__(HermesCLI)
    inst.session_id = "t"
    inst.config = {}
    calls = []
    monkeypatch.setattr(inst, "show_help", lambda: calls.append("help"), raising=False)
    # /help is a pure delegate; process_command should call show_help and return True.
    result = HermesCLI.process_command(inst, "/help")
    assert result is True
    assert calls == ["help"]


def test_unknown_command_falls_through_to_fallback(monkeypatch):
    """A non-table command reaches the quick-command/plugin/skill fallback."""
    inst = HermesCLI.__new__(HermesCLI)
    inst.session_id = "t"
    inst.config = {}
    seen = {}

    def _fake_fallback(cmd_original, cmd_lower):
        seen["hit"] = (cmd_original, cmd_lower)
        return True

    monkeypatch.setattr(inst, "_cmd_fallback", _fake_fallback, raising=False)
    result = HermesCLI.process_command(inst, "/definitely-not-a-command xyz")
    assert result is True
    assert seen["hit"][0] == "/definitely-not-a-command xyz"
