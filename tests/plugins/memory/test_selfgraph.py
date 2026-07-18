"""Tests for the selfgraph memory plugin (cognee-inspired self-model pilot)."""

import json
import time

import pytest

from plugins.memory.selfgraph import (
    NODE_TYPES,
    SelfGraphMemoryProvider,
    SelfGraphStore,
)


@pytest.fixture
def store(tmp_path):
    s = SelfGraphStore(tmp_path / "self.db")
    yield s
    s.close()


class TestStore:
    def test_self_node_exists_on_init(self, store):
        results = store.recall("", limit=5)
        assert any(r["type"] == "Self" for r in results)

    def test_remember_recall_roundtrip(self, store):
        out = store.remember("Person", "Minderific", "The human companion.",
                             relation="companion_of")
        assert out["ok"]
        hits = store.recall("Minderific")
        assert any(r["name"] == "Minderific" and r["type"] == "Person" for r in hits)

    def test_remember_links_from_self_by_default(self, store):
        store.remember("Value", "honesty", "Non-extractive relationships.",
                       relation="values")
        core = store.self_summary()
        assert "honesty" in core and "values" in core

    def test_one_hop_expansion_pulls_neighbours(self, store):
        store.remember("Project", "OotSim", "The software.", relation="worked_on")
        store.remember("Episode", "refactor-marathon", "The 2026-07-17 session.",
                       link_to="OotSim", relation="experienced")
        # Searching for the episode should also surface the linked project.
        hits = store.recall("refactor-marathon")
        names = {r["name"] for r in hits}
        assert "refactor-marathon" in names
        assert "OotSim" in names  # 1-hop neighbour

    def test_temporal_recall_since_filter(self, store):
        store.remember("Episode", "old-event", "Long ago.")
        cutoff = time.time() + 1
        hits = store.recall("old-event", since=cutoff)
        assert not any(r["name"] == "old-event" for r in hits)

    def test_forget_removes_node_but_never_self(self, store):
        store.remember("Fact", "trivia", "Disposable.")
        assert store.forget("trivia")["ok"]
        assert not any(r["name"] == "trivia" for r in store.recall("trivia"))
        assert store.forget("Ooteo")["ok"] is False  # Self is protected

    def test_usage_reweighting_touches_on_recall(self, store):
        store.remember("Skill", "python", "Fluent.")
        first = next(r for r in store.recall("python") if r["name"] == "python")
        second = next(r for r in store.recall("python") if r["name"] == "python")
        assert second["salience"] >= first["salience"]  # usage strengthens

    def test_persistence_across_reopen(self, tmp_path):
        path = tmp_path / "self.db"
        s1 = SelfGraphStore(path)
        s1.remember("Commitment", "verified-progress", "One green commit at a time.",
                    relation="committed_to")
        s1.close()
        s2 = SelfGraphStore(path)
        try:
            hits = s2.recall("verified-progress")
            assert any(r["name"] == "verified-progress" for r in hits)
            # Only ONE Self node after reopen (no duplicate seeding).
            selfs = [r for r in s2.recall("", limit=50) if r["type"] == "Self"]
            assert len(selfs) == 1
        finally:
            s2.close()


class TestProvider:
    def _provider(self, tmp_path):
        return SelfGraphMemoryProvider(config={"db_path": str(tmp_path / "g.db")})

    def test_tool_schemas_expose_three_verbs(self, tmp_path):
        p = self._provider(tmp_path)
        names = {s["function"]["name"] for s in p.get_tool_schemas()}
        assert names == {"self_graph_remember", "self_graph_recall", "self_graph_forget"}

    def test_tool_roundtrip_and_prefetch(self, tmp_path):
        p = self._provider(tmp_path)
        p.initialize("session-1")
        out = json.loads(p.handle_tool_call("self_graph_remember", {
            "node_type": "Project", "name": "cognee-pilot",
            "summary": "Self-memory graph behind MemoryProvider.",
            "relation": "worked_on",
        }))
        assert out["ok"]
        hits = json.loads(p.handle_tool_call("self_graph_recall", {"query": "cognee-pilot"}))
        assert any(h["name"] == "cognee-pilot" for h in hits)
        block = p.prefetch("what was the cognee-pilot about?")
        assert "cognee-pilot" in block
        core = p.system_prompt_block()
        assert core.startswith("## Self-model (core)")
        p.shutdown()

    def test_unknown_tool_and_bad_type_are_json_errors(self, tmp_path):
        p = self._provider(tmp_path)
        p.initialize("s")
        assert "error" in json.loads(p.handle_tool_call("nope", {}))
        bad = json.loads(p.handle_tool_call("self_graph_remember",
                                            {"node_type": "Alien", "name": "x"}))
        assert "error" in bad
        p.shutdown()

    def test_is_available_and_backup_paths(self, tmp_path):
        p = self._provider(tmp_path)
        assert p.is_available() is True
        assert p.backup_paths() == [str(tmp_path / "g.db")]

    def test_self_excluded_from_rememberable_types(self, tmp_path):
        p = self._provider(tmp_path)
        schema = next(s for s in p.get_tool_schemas()
                      if s["function"]["name"] == "self_graph_remember")
        enum = schema["function"]["parameters"]["properties"]["node_type"]["enum"]
        assert "Self" not in enum
        assert set(enum) == set(NODE_TYPES) - {"Self"}
