"""selfgraph — typed self-model graph memory (cognee-inspired pilot).

The pilot from ``docs/cognee-ideas-evaluation.md``: borrow cognee's *model*
(a typed entity+relationship graph with a first-class **Self** node,
episodic/temporal memory, usage-weighted salience) while rejecting its
*infrastructure weight* (no Postgres/Neo4j/embedding service — a single
SQLite file with FTS5, matching the $5-VPS ethos). Runs behind the existing
:class:`agent.memory_provider.MemoryProvider` seam with zero core changes;
enable by installing/enabling the plugin like any other memory provider.

Adopt/adapt decisions implemented here (see the eval doc's table):

- **Typed self-node graph (ADOPT)** — small code-defined ontology
  (:data:`NODE_TYPES`); every graph starts with a ``Self`` node and new
  nodes may link to it (or each other) with typed edges.
- **Episodic/temporal memory (ADOPT)** — ``Episode`` nodes carry
  ``created_at``; ``recall(since=...)`` gives time-aware retrieval.
- **memify-lite (ADAPT)** — every recall/touch bumps ``touch_count`` and
  ``last_touched``; salience combines base salience, usage, and recency
  decay, so salient memories strengthen and trivia fades without a
  background service.
- **remember / recall / forget verbs (ADOPT)** — exposed as agent tools.
- **Dual retrieval (ADAPT)** — FTS5 lexical match seeds the result set,
  then 1-hop graph expansion pulls the connected subgraph (the
  ``GRAPH_COMPLETION``-style step, without an LLM in the loop).
- **Stable core-self block (ADOPT)** — ``system_prompt_block`` renders a
  compact, stable Self summary for the cached prompt tier; volatile recall
  goes through ``prefetch``/tools so the prefix cache never churns.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider

# Small, code-defined ontology (cognee's DataPoint idea, minus Pydantic).
NODE_TYPES = (
    "Self", "Person", "Project", "Episode", "Value", "Commitment",
    "Skill", "Fact",
)

RELATIONS = (
    "values", "worked_on", "companion_of", "changed_from", "knows",
    "committed_to", "learned", "experienced", "related_to",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    salience REAL NOT NULL DEFAULT 0.5,
    created_at REAL NOT NULL,
    last_touched REAL NOT NULL,
    touch_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(type, name)
);
CREATE TABLE IF NOT EXISTS edges (
    src INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    dst INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at REAL NOT NULL,
    PRIMARY KEY (src, dst, relation)
);
CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
    name, summary, content='nodes', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS node_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO node_fts(rowid, name, summary) VALUES (new.id, new.name, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS node_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO node_fts(node_fts, rowid, name, summary)
    VALUES ('delete', old.id, old.name, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS node_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO node_fts(node_fts, rowid, name, summary)
    VALUES ('delete', old.id, old.name, old.summary);
    INSERT INTO node_fts(rowid, name, summary) VALUES (new.id, new.name, new.summary);
END;
"""

# Salience half-life: without touches, effective salience halves this often.
_DECAY_HALF_LIFE_DAYS = 30.0


class SelfGraphStore:
    """SQLite-backed typed graph with a first-class Self node."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        # RLock: remember()/recall() hold the lock and may call self.self_id,
        # which re-enters _ensure_self_node's lock acquisition. A plain Lock
        # deadlocks there (caught by the behavioral test run, not review).
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._ensure_self_node()

    def _ensure_self_node(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM nodes WHERE type='Self' LIMIT 1"
            ).fetchone()
            if row:
                return row[0]
            now = time.time()
            cur = self._conn.execute(
                "INSERT INTO nodes(type, name, summary, salience, created_at, last_touched)"
                " VALUES ('Self', 'Ooteo', 'The agent itself — the center of this self-model graph.', 1.0, ?, ?)",
                (now, now),
            )
            self._conn.commit()
            return cur.lastrowid

    @property
    def self_id(self) -> int:
        return self._ensure_self_node()

    def remember(
        self,
        node_type: str,
        name: str,
        summary: str = "",
        *,
        salience: float = 0.5,
        link_to: Optional[str] = None,
        relation: str = "related_to",
    ) -> Dict[str, Any]:
        """Upsert a typed node; optionally link it (default: from Self)."""
        if node_type not in NODE_TYPES:
            return {"error": f"unknown node type {node_type!r}; use one of {NODE_TYPES}"}
        if relation not in RELATIONS:
            return {"error": f"unknown relation {relation!r}; use one of {RELATIONS}"}
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO nodes(type, name, summary, salience, created_at, last_touched)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(type, name) DO UPDATE SET"
                "   summary=excluded.summary, salience=excluded.salience,"
                "   last_touched=excluded.last_touched,"
                "   touch_count=touch_count+1",
                (node_type, name, summary, salience, now, now),
            )
            node_id = self._conn.execute(
                "SELECT id FROM nodes WHERE type=? AND name=?", (node_type, name)
            ).fetchone()[0]
            src_id = None
            if link_to:
                row = self._conn.execute(
                    "SELECT id FROM nodes WHERE name=? ORDER BY id LIMIT 1", (link_to,)
                ).fetchone()
                src_id = row[0] if row else None
            if src_id is None:
                src_id = self.self_id
            if src_id != node_id:
                self._conn.execute(
                    "INSERT INTO edges(src, dst, relation, weight, created_at)"
                    " VALUES (?,?,?,1.0,?)"
                    " ON CONFLICT(src, dst, relation) DO UPDATE SET weight=weight+0.5",
                    (src_id, node_id, relation, now),
                )
            self._conn.commit()
        return {"ok": True, "id": node_id, "type": node_type, "name": name}

    def _effective_salience(self, salience: float, last_touched: float,
                            touch_count: int, now: float) -> float:
        """memify-lite: usage strengthens, recency decays."""
        age_days = max(0.0, (now - last_touched) / 86400.0)
        decay = math.pow(0.5, age_days / _DECAY_HALF_LIFE_DAYS)
        usage = min(0.5, 0.05 * touch_count)
        return min(1.5, salience * decay + usage)

    def recall(
        self,
        query: str,
        *,
        limit: int = 8,
        since: Optional[float] = None,
        node_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """FTS seed match + 1-hop graph expansion, ranked by effective salience."""
        now = time.time()
        with self._lock:
            seeds: List[int] = []
            if query.strip():
                # FTS5 bareword query; quote to disable operators from user text.
                fts_query = " ".join(
                    f'"{t}"' for t in query.replace('"', " ").split() if t
                ) or '""'
                try:
                    seeds = [r[0] for r in self._conn.execute(
                        "SELECT rowid FROM node_fts WHERE node_fts MATCH ? LIMIT ?",
                        (fts_query, limit * 2),
                    ).fetchall()]
                except sqlite3.OperationalError:
                    seeds = []
            else:
                seeds = [r[0] for r in self._conn.execute(
                    "SELECT id FROM nodes ORDER BY last_touched DESC LIMIT ?",
                    (limit * 2,),
                ).fetchall()]
            # 1-hop expansion: pull neighbours of every seed.
            expanded = set(seeds)
            if seeds:
                marks = ",".join("?" * len(seeds))
                for src, dst in self._conn.execute(
                    f"SELECT src, dst FROM edges WHERE src IN ({marks}) OR dst IN ({marks})",
                    seeds + seeds,
                ).fetchall():
                    expanded.add(src)
                    expanded.add(dst)
            if not expanded:
                return []
            marks = ",".join("?" * len(expanded))
            where = [f"id IN ({marks})"]
            params: List[Any] = list(expanded)
            if since is not None:
                where.append("created_at >= ?")
                params.append(since)
            if node_type is not None:
                where.append("type = ?")
                params.append(node_type)
            rows = self._conn.execute(
                "SELECT id, type, name, summary, salience, created_at, last_touched, touch_count"
                f" FROM nodes WHERE {' AND '.join(where)}",
                params,
            ).fetchall()
            results = []
            for (nid, ntype, name, summary, salience, created, touched, count) in rows:
                results.append({
                    "id": nid, "type": ntype, "name": name, "summary": summary,
                    "salience": round(self._effective_salience(salience, touched, count, now), 3),
                    "created_at": created,
                    "seed": nid in seeds,
                })
            results.sort(key=lambda r: (not r["seed"], -r["salience"]))
            results = results[:limit]
            # Touch retrieved nodes (usage reweighting).
            if results:
                marks = ",".join("?" * len(results))
                self._conn.execute(
                    f"UPDATE nodes SET touch_count=touch_count+1, last_touched=? WHERE id IN ({marks})",
                    [now] + [r["id"] for r in results],
                )
                self._conn.commit()
            return results

    def forget(self, name: str, node_type: Optional[str] = None) -> Dict[str, Any]:
        """Delete a node (and its edges) by name — intentional curation."""
        with self._lock:
            where, params = "name=?", [name]
            if node_type:
                where += " AND type=?"
                params.append(node_type)
            row = self._conn.execute(
                f"SELECT id, type FROM nodes WHERE {where} LIMIT 1", params
            ).fetchone()
            if not row:
                return {"ok": False, "error": f"no node named {name!r}"}
            if row[1] == "Self":
                return {"ok": False, "error": "the Self node cannot be forgotten"}
            self._conn.execute("DELETE FROM nodes WHERE id=?", (row[0],))
            self._conn.commit()
        return {"ok": True, "forgotten": name}

    def self_summary(self, *, limit: int = 6) -> str:
        """Compact, stable core-self block: strongest edges from Self."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT e.relation, n.type, n.name, n.summary"
                " FROM edges e JOIN nodes n ON n.id = e.dst"
                " WHERE e.src=? ORDER BY e.weight DESC, n.salience DESC LIMIT ?",
                (self.self_id, limit),
            ).fetchall()
        if not rows:
            return ""
        lines = [f"- {rel} → {ntype} “{name}”" + (f": {summary}" if summary else "")
                 for rel, ntype, name, summary in rows]
        return "\n".join(lines)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class SelfGraphMemoryProvider(MemoryProvider):
    """MemoryProvider seam wrapper around :class:`SelfGraphStore`."""

    def __init__(self, config: Optional[dict] = None):
        self._config = config or {}
        self._store: Optional[SelfGraphStore] = None

    @property
    def name(self) -> str:
        return "selfgraph"

    def is_available(self) -> bool:
        return True  # stdlib sqlite3 + FTS5; no network, no keys

    def _db_path(self) -> Path:
        configured = self._config.get("db_path")
        if configured:
            return Path(configured).expanduser()
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home()) / "selfgraph" / "self.db"

    def initialize(self, session_id: str, **kwargs) -> None:
        if self._store is None:
            self._store = SelfGraphStore(self._db_path())

    def _require_store(self) -> SelfGraphStore:
        if self._store is None:
            self._store = SelfGraphStore(self._db_path())
        return self._store

    def system_prompt_block(self) -> str:
        core = self._require_store().self_summary()
        if not core:
            return ""
        # Stable tier: only the strongest Self edges, so the cached prompt
        # prefix doesn't churn turn-to-turn.
        return "## Self-model (core)\n" + core

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not query.strip():
            return ""
        results = self._require_store().recall(query, limit=5)
        if not results:
            return ""
        lines = [
            f"- [{r['type']}] {r['name']}"
            + (f": {r['summary']}" if r["summary"] else "")
            for r in results
        ]
        return "Recalled from the self-model graph (background reference):\n" + "\n".join(lines)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "self_graph_remember",
                    "description": (
                        "Persist a typed node in the self-model graph (Person, Project, "
                        "Episode, Value, Commitment, Skill, Fact), optionally linked from "
                        "the Self node or a named node with a typed relation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "node_type": {"type": "string", "enum": [t for t in NODE_TYPES if t != "Self"]},
                            "name": {"type": "string"},
                            "summary": {"type": "string"},
                            "salience": {"type": "number", "minimum": 0, "maximum": 1},
                            "link_to": {"type": "string", "description": "Name of an existing node to link from (defaults to Self)"},
                            "relation": {"type": "string", "enum": list(RELATIONS)},
                        },
                        "required": ["node_type", "name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "self_graph_recall",
                    "description": (
                        "Recall from the self-model graph: lexical match plus 1-hop "
                        "graph expansion, ranked by usage-weighted salience. "
                        "Optionally filter by node type or created-after timestamp."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "node_type": {"type": "string", "enum": list(NODE_TYPES)},
                            "since": {"type": "number", "description": "Unix timestamp lower bound (temporal recall)"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "self_graph_forget",
                    "description": "Intentionally remove a node (and its edges) from the self-model graph.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "node_type": {"type": "string", "enum": [t for t in NODE_TYPES if t != "Self"]},
                        },
                        "required": ["name"],
                    },
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        store = self._require_store()
        try:
            if tool_name == "self_graph_remember":
                return json.dumps(store.remember(
                    args.get("node_type", "Fact"),
                    args.get("name", ""),
                    args.get("summary", ""),
                    salience=float(args.get("salience", 0.5)),
                    link_to=args.get("link_to"),
                    relation=args.get("relation", "related_to"),
                ), ensure_ascii=False)
            if tool_name == "self_graph_recall":
                return json.dumps(store.recall(
                    args.get("query", ""),
                    limit=int(args.get("limit", 8)),
                    since=args.get("since"),
                    node_type=args.get("node_type"),
                ), ensure_ascii=False)
            if tool_name == "self_graph_forget":
                return json.dumps(store.forget(
                    args.get("name", ""), args.get("node_type"),
                ), ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001 — tool boundary, surface as error
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return json.dumps({"error": f"unknown tool {tool_name}"}, ensure_ascii=False)

    def shutdown(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def backup_paths(self) -> List[str]:
        return [str(self._db_path())]


def _load_plugin_config() -> dict:
    from hermes_constants import get_hermes_home
    config_path = Path(get_hermes_home()) / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        from hermes_cli.config import cfg_get
        with open(config_path, encoding="utf-8-sig") as f:
            all_config = yaml.safe_load(f) or {}
        return cfg_get(all_config, "plugins", "selfgraph", default={}) or {}
    except Exception:
        return {}


def register(ctx) -> None:
    """Register the self-graph memory provider with the plugin system."""
    provider = SelfGraphMemoryProvider(config=_load_plugin_config())
    ctx.register_memory_provider(provider)
