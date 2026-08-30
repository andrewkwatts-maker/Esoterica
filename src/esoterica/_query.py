"""Core query engine backed by a baked SQLite database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from eyecore import BaseDB, TopicGraph, CorpusManager

_DATA_DIR = Path(__file__).parent / "_data"

# Baked snapshot hosted as a GitHub Release asset, downloaded lazily on first
# query. Firestore serves only the diff layer on top (see Refresh()).
_DATA_URL = (
    "https://github.com/andrewkwatts-maker/Esoterica/releases/download/"
    "data-v1.1.0/esoterica.db.gz"
)

# Firestore collections this package mirrors (must match scripts/bake.py).
MAGIC_COLLECTIONS = [
    "spells", "rituals", "magic", "traditions", "grimoires", "herbs",
    "ingredients", "artifacts", "practitioners",
]

_COLLECTION_TYPES = {
    "spells": "spell", "rituals": "ritual", "magic": "tradition",
    "traditions": "tradition", "grimoires": "grimoire", "herbs": "ingredient",
    "ingredients": "ingredient", "artifacts": "artifact",
    "practitioners": "practitioner",
}

_BASE = BaseDB("esoterica", gz_path=_DATA_DIR / "esoterica.db.gz", remote_url=_DATA_URL)


def Refresh(api_key: str = "") -> int:
    """Pull entities changed in Firestore since the bake (or last Refresh)
    and merge them into the local database. Returns entities applied."""
    from datetime import datetime, timezone

    from eyecore import apply_deltas, fetch_deltas, get_meta

    conn = _BASE.conn
    since = get_meta(conn, "last_sync") or get_meta(conn, "generated_at")
    if not since:
        raise RuntimeError(
            "This database predates delta support — re-bake with the current "
            "scripts/bake.py (writes meta.generated_at)."
        )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    docs = fetch_deltas("eyesofazrael", MAGIC_COLLECTIONS, since, api_key)
    return apply_deltas(conn, docs, _COLLECTION_TYPES, now)

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
        _CORPUS = CorpusManager("esoterica", _BASE.conn)
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


def ByTradition(mythology: str, limit: int = 500) -> list[dict]:
    rows = _BASE.fetchall(
        "SELECT data FROM entities WHERE lower(mythology) = lower(?) LIMIT ?",
        (mythology, limit),
    )
    return _rows_data(rows)


ByCategory = ByTradition
ByMythology = ByTradition


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


def AllSpells(mythology: str | None = None, limit: int = 500) -> list[dict]:
    return ByType("spell", mythology, limit)


def AllRituals(mythology: str | None = None, limit: int = 500) -> list[dict]:
    return ByType("ritual", mythology, limit)


def AllTraditions(limit: int = 500) -> list[dict]:
    return ByType("tradition", limit=limit)


def Count(entity_type: str | None = None) -> int:
    if entity_type:
        return _BASE.fetchone(
            "SELECT COUNT(*) FROM entities WHERE type = ?", (entity_type,)
        )[0]
    return _BASE.fetchone("SELECT COUNT(*) FROM entities")[0]


def GetRandom(entity_type: str | None = None, mythology: str | None = None) -> dict | None:
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
        row = _BASE.fetchone("SELECT data FROM entities ORDER BY RANDOM() LIMIT 1")
    return _row_data(row)


def GetFuzzy(query: str, limit: int = 5) -> list[dict]:
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
    if field not in ("mythology", "type"):
        raise ValueError("field must be 'mythology' or 'type'")
    rows = _BASE.fetchall(
        f"SELECT {field}, COUNT(*) as count FROM entities "
        f"WHERE {field} IS NOT NULL GROUP BY {field} ORDER BY count DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def GetAll(entity_type: str | None = None, mythology: str | None = None) -> list[dict]:
    if entity_type and mythology:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE type=? AND lower(mythology)=lower(?)",
            (entity_type, mythology),
        )
    elif entity_type:
        rows = _BASE.fetchall("SELECT data FROM entities WHERE type=?", (entity_type,))
    elif mythology:
        rows = _BASE.fetchall(
            "SELECT data FROM entities WHERE lower(mythology)=lower(?)", (mythology,)
        )
    else:
        rows = _BASE.fetchall("SELECT data FROM entities")
    return _rows_data(rows)


def GetTopics(query: str | None = None, limit: int = 50) -> list[dict]:
    graph = _get_graph()
    if query:
        return graph.search(query, limit=limit)
    try:
        rows = _BASE.fetchall(
            "SELECT id, name, type, parent_id, description, data FROM topics LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return graph.all_roots()[:limit]


def GetRelated(name_or_id: str, relation: str | None = None) -> list[dict]:
    graph = _get_graph()
    topic = graph.get(name_or_id)
    if topic is None:
        topic = graph.find(name_or_id)
    if topic is None:
        return []
    return graph.get_related(topic["id"], relation=relation)


def GetTopicTree(root: str) -> dict:
    graph = _get_graph()
    topic = graph.get(root)
    if topic is None:
        topic = graph.find(root)
    if topic is None:
        return {}
    return graph.subtree(topic["id"])


def SearchCorpus(query: str, corpus: str | None = None, limit: int = 20) -> list[dict]:
    return _get_corpus().search(query, corpus_id=corpus, limit=limit)


def FetchCorpus(name: str) -> str:
    cm = _get_corpus()
    path = cm.fetch(name)
    cm.index(name)
    return str(path)


def ListCorpuses() -> list[dict]:
    return _get_corpus().list_available()
