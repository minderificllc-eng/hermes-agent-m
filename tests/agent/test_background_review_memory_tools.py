"""Tests for the background-review deliberate-write seam.

Providers that declare non-empty ``background_review_instructions`` share
their live instances with the review fork through
``_ReviewToolsOnlyMemoryManager`` — tool dispatch works, but every
ambient/lifecycle hook is a no-op, so the skip_memory isolation
(harness prompt never leaks into providers; fork teardown never shuts
down the parent's providers) is preserved.
"""

from types import SimpleNamespace
from typing import Any, Dict, List

from agent.background_review import (
    _build_review_memory_manager,
    _ReviewToolsOnlyMemoryManager,
)
from agent.memory_manager import MemoryManager, inject_memory_provider_tools
from agent.memory_provider import MemoryProvider
from plugins.memory.selfgraph import SelfGraphMemoryProvider


class _StubProvider(MemoryProvider):
    """Instrumented provider that opts in to background-review writes."""

    background_review_instructions = "Stub: persist things deliberately."

    def __init__(self):
        self.calls: List[str] = []

    @property
    def name(self) -> str:
        return "stub"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        self.calls.append("initialize")

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": "stub_write", "description": "write", "parameters": {}}]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        self.calls.append(f"tool:{tool_name}")
        return '{"ok": true}'

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        self.calls.append("prefetch")
        return "leaked"

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None):
        self.calls.append("sync_turn")

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        self.calls.append("on_turn_start")

    def on_session_end(self, messages) -> None:
        self.calls.append("on_session_end")

    def shutdown(self) -> None:
        self.calls.append("shutdown")


class _OptedOutProvider(_StubProvider):
    background_review_instructions = ""

    @property
    def name(self) -> str:
        return "opted-out"


def _agent_with(*providers) -> SimpleNamespace:
    mm = MemoryManager()
    for p in providers:
        mm.add_provider(p)
    return SimpleNamespace(_memory_manager=mm)


class TestBuildReviewMemoryManager:
    def test_no_manager_on_parent(self):
        manager, instructions = _build_review_memory_manager(SimpleNamespace())
        assert manager is None and instructions == []

    def test_no_opted_in_providers(self):
        manager, instructions = _build_review_memory_manager(
            _agent_with(_OptedOutProvider())
        )
        assert manager is None and instructions == []

    def test_opted_in_provider_shares_instance_and_instructions(self):
        stub = _StubProvider()
        manager, instructions = _build_review_memory_manager(_agent_with(stub))
        assert manager is not None
        assert instructions == ["Stub: persist things deliberately."]
        assert manager.has_tool("stub_write")
        # The SAME instance is shared — dispatch reaches the parent's provider.
        manager.handle_tool_call("stub_write", {})
        assert "tool:stub_write" in stub.calls

    def test_selfgraph_provider_opts_in_and_dispatch_writes_shared_store(self, tmp_path):
        provider = SelfGraphMemoryProvider(config={"db_path": str(tmp_path / "self.db")})
        manager, instructions = _build_review_memory_manager(_agent_with(provider))
        assert manager is not None
        assert instructions and "self_graph_remember" in instructions[0]
        assert manager.get_all_tool_names() == {
            "self_graph_remember", "self_graph_recall", "self_graph_forget",
        }
        manager.handle_tool_call(
            "self_graph_remember",
            {"node_type": "Project", "name": "OotSim", "summary": "The software."},
        )
        # Visible through the provider's own store — same instance, same DB.
        hits = provider._require_store().recall("OotSim")
        assert any(r["name"] == "OotSim" for r in hits)


class TestToolsOnlyManagerIsolation:
    def test_ambient_hooks_never_reach_the_provider(self):
        stub = _StubProvider()
        manager, _ = _build_review_memory_manager(_agent_with(stub))
        assert manager.build_system_prompt() == ""
        assert manager.prefetch_all("harness prompt") == ""
        manager.queue_prefetch_all("harness prompt")
        manager.sync_all("user", "assistant")
        manager.on_turn_start(1, "harness prompt")
        manager.on_session_end([])
        manager.commit_session_boundary_async([])
        manager.notify_memory_tool_write("memory", {}, "ok")
        manager.initialize_all(session_id="x")
        manager.shutdown_all()
        assert manager.flush_pending() is True
        ambient = [c for c in stub.calls if not c.startswith("tool:")]
        assert ambient == [], f"ambient hooks leaked through: {ambient}"

    def test_every_public_manager_method_is_classified(self):
        """Drift guard: a new public MemoryManager method must be explicitly
        either dispatch (allowlist below) or ambient (overridden as a no-op in
        _ReviewToolsOnlyMemoryManager). Otherwise the review fork could grow a
        silent side-effect path into the parent's live providers."""
        dispatch_allowlist = {
            "add_provider", "providers", "get_provider",
            "get_all_tool_schemas", "get_all_tool_names",
            "has_tool", "handle_tool_call",
        }
        overridden = set(vars(_ReviewToolsOnlyMemoryManager))
        unclassified = [
            name for name, member in vars(MemoryManager).items()
            if not name.startswith("_")
            and (callable(member) or isinstance(member, property))
            and name not in dispatch_allowlist
            and name not in overridden
        ]
        assert unclassified == [], (
            f"Unclassified public MemoryManager members: {unclassified}. "
            "Add each to the dispatch allowlist (if it has no provider side "
            "effects) or override it as a no-op in _ReviewToolsOnlyMemoryManager."
        )


class TestToolInjectionIntoFork:
    def test_inject_adds_schemas_and_valid_names(self):
        stub = _StubProvider()
        manager, _ = _build_review_memory_manager(_agent_with(stub))
        fork = SimpleNamespace(
            _memory_manager=manager,
            tools=[],
            enabled_toolsets=None,
            valid_tool_names=set(),
        )
        added = inject_memory_provider_tools(fork)
        assert added == 1
        assert fork.tools[0]["function"]["name"] == "stub_write"
        assert "stub_write" in fork.valid_tool_names


class TestBaseClassDefault:
    def test_providers_are_opted_out_by_default(self):
        assert MemoryProvider.background_review_instructions == ""
