"""Core query engine backed by a baked SQLite database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from eyecore import BaseDB, TopicGraph, CorpusManager

_DATA_DIR = Path(__file__).parent / "_data"

_BASE = BaseDB("apocrypha", gz_path=_DATA_DIR / "apocrypha.db.gz")

# Lazy singletons for graph and corpus
_GRAPH: TopicGraph | None = None
_CORPUS: CorpusManager | None = None


def _get_graph() -> TopicGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = TopicGraph(_BASE.conn)
    return _GRAPH


def _get_corpus() -> CorpusManager:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = CorpusManager("apocrypha", _BASE.conn)
    return _CORPUS


def _row_data(row) -> dict | None:
    return json.loads(row["data"]) if row else None


def _rows_data(rows) -> list[dict]:
    return [json.loads(r["data"]) for r in rows]


def Get(name: str) -> dict | None:
    row = _BASE.fetchone(
        "SELECT data FROM entities WHERE lower(name) = lower(?)", (name,)
    )
    if row:
        return _row_data(row)
    row = _BASE.fetchone(
        "SELECT data FROM entities WHERE lower(name) LIKE lower(?)", (f"%{name}%",)
    )
    return _row_data(row)


def _typed(query: str, *types: str) -> dict | None:
    ph = ",".join("?" * len(types))
    row = _BASE.fetchone(
        f"SELECT data FROM entities WHERE lower(name) = lower(?) AND type IN ({ph})",
        (query, *types),
    )
    if row:
        return _row_data(row)
    row = _BASE.fetchone(
        f"SELECT data FROM entities WHERE lower(name) LIKE lower(?) AND type IN ({ph})",
        (f"%{query}%", *types),
    )
    if row:
        return _row_data(row)
    row = _BASE.fetchone(
        f"SELECT data FROM entities WHERE lower(domains_text) LIKE lower(?) AND type IN ({ph})",
        (f"%{query}%", *types),
    )
    return _row_data(row)


def Search(query: str, limit: int = 20) -> list[dict]:
    try:
        rows = _BASE.fetchall(
            """SELECT e.data FROM entities e
               INNER JOIN (
                   SELECT id, rank FROM entities_fts WHERE entities_fts MATCH ?
                   ORDER BY rank
               ) fts ON e.id = fts.id
               LIMIT ?""",
            (query, limit),
        )
        return _rows_data(rows)
    except sqlite3.OperationalError:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE lower(search_text) LIKE lower(?) LIMIT ?",
            (f"%{query}%", limit),
        )
        return _rows_data(rows)


def ByMythology(mythology: str, limit: int = 500) -> list[dict]:
    rows = _BASE.fetchall(
        "SELECT data FROM entities WHERE lower(mythology) = lower(?) LIMIT ?",
        (mythology, limit),
    )
    return _rows_data(rows)


# ByCategory and ByEra are aliases pointing to ByMythology (same column, different semantic name)
ByCategory = ByMythology
ByEra = ByMythology


def ByType(entity_type: str, mythology: str | None = None, limit: int = 500) -> list[dict]:
    if mythology:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE type = ? AND lower(mythology) = lower(?) LIMIT ?",
            (entity_type, mythology, limit),
        )
    else:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE type = ? LIMIT ?",
            (entity_type, limit),
        )
    return _rows_data(rows)


def AllGods(mythology: str | None = None, limit: int = 500) -> list[dict]:
    return ByType("deity", mythology, limit)


def AllCreatures(mythology: str | None = None, limit: int = 500) -> list[dict]:
    return ByType("creature", mythology, limit)


def AllHeroes(mythology: str | None = None, limit: int = 500) -> list[dict]:
    return ByType("hero", mythology, limit)


def Count(entity_type: str | None = None) -> int:
    if entity_type:
        return _BASE.fetchone(
            "SELECT COUNT(*) FROM entities WHERE type = ?", (entity_type,)
        )[0]
    return _BASE.fetchone("SELECT COUNT(*) FROM entities")[0]


# ── Extended helpers ──────────────────────────────────────────────────────────

def GetRandom(entity_type: str | None = None, mythology: str | None = None) -> dict | None:
    """Return a random entity, optionally filtered by type and/or mythology."""
    if entity_type and mythology:
        row = _BASE.fetchone(
            "SELECT data FROM entities WHERE type=? AND lower(mythology)=lower(?) ORDER BY RANDOM() LIMIT 1",
            (entity_type, mythology),
        )
    elif entity_type:
        row = _BASE.fetchone(
            "SELECT data FROM entities WHERE type=? ORDER BY RANDOM() LIMIT 1",
            (entity_type,),
        )
    elif mythology:
        row = _BASE.fetchone(
            "SELECT data FROM entities WHERE lower(mythology)=lower(?) ORDER BY RANDOM() LIMIT 1",
            (mythology,),
        )
    else:
        row = _BASE.fetchone(
            "SELECT data FROM entities ORDER BY RANDOM() LIMIT 1"
        )
    return _row_data(row)


def GetFuzzy(query: str, limit: int = 5) -> list[dict]:
    """Fuzzy name search — prefix FTS matching with LIKE fallback."""
    try:
        rows = _BASE.fetchall(
            """SELECT e.data FROM entities e
               INNER JOIN (
                   SELECT id, rank FROM entities_fts WHERE name MATCH ?
                   ORDER BY rank
               ) fts ON e.id = fts.id
               LIMIT ?""",
            (query + "*", limit),
        )
        if rows:
            return _rows_data(rows)
    except sqlite3.OperationalError:
        pass
    rows = _BASE.fetchall(
        "SELECT data FROM entities WHERE lower(name) LIKE lower(?) LIMIT ?",
        (f"%{query}%", limit),
    )
    return _rows_data(rows)


def GetMost(field: str = "mythology", limit: int = 10) -> list[dict]:
    """Top groupings by entity count.

    GetMost("mythology") -> [{mythology: "conspiracies", count: 120}, ...]
    GetMost("type")      -> [{type: "theory", count: 80}, ...]
    """
    if field not in ("mythology", "type"):
        raise ValueError("field must be 'mythology' or 'type'")
    rows = _BASE.fetchall(
        f"SELECT {field}, COUNT(*) as count FROM entities "
        f"WHERE {field} IS NOT NULL GROUP BY {field} ORDER BY count DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def GetAll(entity_type: str | None = None, mythology: str | None = None) -> list[dict]:
    """Return every matching entity with no row limit. Large result sets possible."""
    if entity_type and mythology:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE type=? AND lower(mythology)=lower(?)",
            (entity_type, mythology),
        )
    elif entity_type:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE type=?", (entity_type,)
        )
    elif mythology:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE lower(mythology)=lower(?)", (mythology,)
        )
    else:
        rows = _BASE.fetchall("SELECT data FROM entities")
    return _rows_data(rows)


# ── Topic graph functions ─────────────────────────────────────────────────────

def GetTopics(query: str | None = None, limit: int = 50) -> list[dict]:
    """Return topics from the topic graph, optionally filtered by query string."""
    graph = _get_graph()
    if query:
        return graph.search(query, limit=limit)
    # Return all roots when no query given, then fill to limit with all topics
    try:
        rows = _BASE.fetchall(
            "SELECT id, name, type, parent_id, description, data FROM topics LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return graph.all_roots()[:limit]


def GetRelated(name_or_id: str, relation: str | None = None) -> list[dict]:
    """Return topics related to a given topic (by name or id)."""
    graph = _get_graph()
    # Try to resolve by id first, then by name
    topic = graph.get(name_or_id)
    if topic is None:
        topic = graph.find(name_or_id)
    if topic is None:
        return []
    return graph.get_related(topic["id"], relation=relation)


def GetTopicTree(root: str) -> dict:
    """Return the full subtree rooted at the named or id'd topic."""
    graph = _get_graph()
    topic = graph.get(root)
    if topic is None:
        topic = graph.find(root)
    if topic is None:
        return {}
    return graph.subtree(topic["id"])


def SearchCorpus(query: str, corpus: str | None = None, limit: int = 20) -> list[dict]:
    """Search indexed text corpuses for the given query."""
    cm = _get_corpus()
    return cm.search(query, corpus_id=corpus, limit=limit)


def FetchCorpus(name: str) -> str:
    """Download and index a corpus by name. Returns local path as string."""
    cm = _get_corpus()
    path = cm.fetch(name)
    cm.index(name)
    return str(path)


def ListCorpuses() -> list[dict]:
    """List all available corpuses (registered in the DB)."""
    cm = _get_corpus()
    return cm.list_available()
