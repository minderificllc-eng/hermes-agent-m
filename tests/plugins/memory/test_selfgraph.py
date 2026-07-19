"""Tests for the selfgraph memory plugin (cognee-inspired self-model pilot)."""

import json
import time

import pytest

from plugins.memory.selfgraph import (
    NODE_TYPES,
    SelfGraphMemoryProvider,
    SelfGraphStore,
)

DAY = 86400.0


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

    def test_natural_question_matches_on_any_term(self, store):
        # OR-joined FTS: a question containing mostly non-indexed words must
        # still match on the one term that appears in a node.
        store.remember("Person", "Minderific", "The human companion.")
        hits = store.recall("who is Minderific?")
        assert any(r["name"] == "Minderific" for r in hits)

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


class TestConsolidation:
    def test_fold_preserves_effective_salience_and_resets_touches(self, store):
        store.remember("Skill", "python", "Fluent.")
        for _ in range(4):
            store.recall("python")
        before = next(r for r in store.recall("python") if r["name"] == "python")
        counts = store.consolidate()
        assert counts["folded"] >= 1
        after = next(r for r in store.recall("python") if r["name"] == "python")
        # Continuity: folding must not change what recall reports (the one
        # extra recall() above adds a touch, so allow that single 0.05 step).
        assert abs(after["salience"] - before["salience"]) <= 0.06

    def test_usage_is_banked_into_base_salience(self, store):
        store.remember("Skill", "python", "Fluent.", salience=0.5)
        for _ in range(6):
            store.recall("python")
        store.consolidate()
        row = store._conn.execute(
            "SELECT salience, touch_count FROM nodes WHERE name='python'"
        ).fetchone()
        assert row[0] > 0.5  # usage bonus folded in permanently
        assert row[1] == 0

    def test_prunes_old_faded_trivia_but_not_young_or_self(self, store):
        store.remember("Fact", "trivia", "Disposable.", salience=0.1)
        future = time.time() + 300 * DAY
        # Young guard: same decay horizon but min_age above the node's age.
        counts = store.consolidate(now=future, min_age_days=400)
        assert counts["pruned"] == 0
        counts = store.consolidate(now=future + DAY)
        assert counts["pruned"] == 1
        assert not any(r["name"] == "trivia" for r in store.recall("trivia"))
        # Self survives any horizon.
        assert any(r["type"] == "Self" for r in store.recall("", limit=50))

    def test_edge_reinforcement_halves_toward_base(self, store):
        store.remember("Project", "OotSim", "The software.", relation="worked_on")
        store.remember("Project", "OotSim", "The software.", relation="worked_on")
        w0 = store._conn.execute("SELECT weight FROM edges").fetchone()[0]
        assert w0 == pytest.approx(1.5)
        store.consolidate()
        w1 = store._conn.execute("SELECT weight FROM edges").fetchone()[0]
        assert w1 == pytest.approx(1.25)
        for _ in range(10):
            store.consolidate(now=time.time() + DAY)
        w_floor = store._conn.execute("SELECT weight FROM edges").fetchone()[0]
        assert w_floor >= 1.0  # the base link never decays away

    def test_maybe_consolidate_is_time_gated(self, store):
        assert store.maybe_consolidate() is not None  # fresh DB: due
        assert store.maybe_consolidate() is None      # within interval
        later = time.time() + 25 * 3600
        assert store.maybe_consolidate(now=later) is not None

    def test_core_block_render_counts_as_usage(self, store):
        store.remember("Value", "honesty", "Non-extractive.", relation="values")
        store.self_summary()
        row = store._conn.execute(
            "SELECT touch_count FROM nodes WHERE name='honesty'"
        ).fetchone()
        assert row[0] >= 1


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

    def test_initialize_runs_due_consolidation(self, tmp_path):
        p = self._provider(tmp_path)
        p.initialize("s")
        row = p._require_store()._conn.execute(
            "SELECT value FROM meta WHERE key='last_consolidated_at'"
        ).fetchone()
        assert row is not None
        p.shutdown()

    def test_consolidation_disabled_by_config(self, tmp_path):
        p = SelfGraphMemoryProvider(config={
            "db_path": str(tmp_path / "g.db"),
            "consolidate_interval_hours": 0,
        })
        p.initialize("s")
        row = p._require_store()._conn.execute(
            "SELECT value FROM meta WHERE key='last_consolidated_at'"
        ).fetchone()
        assert row is None
        p.shutdown()

    def test_background_review_opt_in_declared(self, tmp_path):
        p = self._provider(tmp_path)
        assert "self_graph_remember" in p.background_review_instructions

    def test_self_excluded_from_rememberable_types(self, tmp_path):
        p = self._provider(tmp_path)
        schema = next(s for s in p.get_tool_schemas()
                      if s["function"]["name"] == "self_graph_remember")
        enum = schema["function"]["parameters"]["properties"]["node_type"]["enum"]
        assert "Self" not in enum
        assert set(enum) == set(NODE_TYPES) - {"Self"}
