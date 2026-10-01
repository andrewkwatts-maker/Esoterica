"""Core query engine backed by a baked SQLite database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from eyecore import BaseDB, TopicGraph, CorpusManager

from ._backend import rank_entities

_DATA_DIR = Path(__file__).parent / "_data"

# Baked snapshot hosted as a GitHub Release asset, downloaded lazily on first
# query. Firestore serves only the diff layer on top (see Refresh()).
_DATA_URL = (
    "https://github.com/andrewkwatts-maker/Esoterica/releases/download/"
    "data-v1.1.0/esoterica.db.gz"
)

# SHA-256 of the release asset above, verified before the download is cached.
_DATA_SHA256 = "2ff185daa39da99345d1f35bf86075f6ae585ea6c14ac0258083796cde084d53"

# Firestore collections this package mirrors (must match scripts/bake.py).
MAGIC_COLLECTIONS = [
    "spells", "rituals", "magic", "traditions", "grimoires", "herbs",
    "ingredients", "artifacts", "practitioners",
]

# Collection -> entity type. This is only the *fallback* for a document that
# carries no `type` of its own, so it must agree with the type the documents
# actually declare -- otherwise delta-synced rows land under a type nothing
# queries, sitting invisibly beside their baked siblings.
#
# `herbs` and `magic` are legacy collection names from the azrael split and
# were mapped onto `ingredient`/`tradition`. Every one of the 127 baked herb
# rows and 106 baked magic rows declares `type: "herb"` / `type: "magic"`, so
# the documents are authoritative and the mapping was wrong. The public
# getters below accept both spellings so nothing that worked before breaks.
_COLLECTION_TYPES = {
    "spells": "spell", "rituals": "ritual", "magic": "magic",
    "traditions": "tradition", "grimoires": "grimoire", "herbs": "herb",
    "ingredients": "ingredient", "artifacts": "artifact",
    "practitioners": "practitioner",
}

# Types the baked snapshot uses interchangeably, for the getters that must
# span both. Left of the colon is what callers ask for.
_TYPE_ALIASES = {
    "ingredient": ("ingredient", "herb"),
    "tradition": ("tradition", "magic"),
}


def _expand_types(*types: str) -> tuple[str, ...]:
    """Every stored spelling of each requested type, de-duplicated."""
    out: list[str] = []
    for t in types:
        out.extend(_TYPE_ALIASES.get(t, (t,)))
    return tuple(dict.fromkeys(out))


_BASE = BaseDB(
    "esoterica",
    gz_path=_DATA_DIR / "esoterica.db.gz",
    remote_url=_DATA_URL,
    remote_sha256=_DATA_SHA256,
)


def Refresh(api_key: str = "") -> int:
    """Pull entities changed in Firestore since the bake (or last Refresh)
    and merge them into the local database. Returns entities applied."""
    from datetime import datetime, timezone

    from eyecore import apply_deltas, fetch_deltas, get_meta

    conn = _BASE.conn
    since = get_meta(conn, "last_sync") or get_meta(conn, "generated_at")
    if not since:
        raise RuntimeError(
            "This database predates delta support -- re-bake with the current "
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


# How wide a candidate pool to score for a request of `limit` results.
# Re-ranking only earns its keep if it can see rows the database's own
# ordering would have cut off, so the pool is deliberately wider than the
# answer -- but capped, because the caller asked for a page and not a scan.
_RANK_POOL_FACTOR = 5
_RANK_POOL_CAP = 500

# Columns `_reranked` needs. `domains_text` stands in for the description:
# the entities table has no description column, and domains_text is the per-row
# prose blob the bake writes from domains, abilities, powers and tags.
_RANK_COLUMNS = "e.name, e.domains_text, e.search_text, e.data"


def _rank_pool(limit: int) -> int:
    """Candidate count to fetch when `limit` results are wanted."""
    if limit <= 0:
        return limit
    return max(limit, min(limit * _RANK_POOL_FACTOR, _RANK_POOL_CAP))


def _reranked(rows, query: str, limit: int) -> list[dict]:
    """Order `rows` by the Rust relevance model and cut to `limit`.

    Rows the scorer gives zero are appended in their original order rather
    than dropped. The FTS tokenizer folds diacritics and matches whole tokens,
    so it legitimately finds rows that a substring scorer cannot; discarding
    those would be a silent regression against the SQL-only behaviour this
    replaces. Ranking may only reorder, never lose.
    """
    if not rows or not query or limit <= 0:
        # A non-positive limit keeps SQL's own semantics, where a negative
        # LIMIT means "no limit" -- re-ranking must not quietly redefine that.
        return _rows_data(rows)
    triples = [
        (r["name"] or "", r["domains_text"] or "", r["search_text"] or "")
        for r in rows
    ]
    order = [index for index, _score in rank_entities(triples, query, limit)]
    scored = set(order)
    order.extend(index for index in range(len(rows)) if index not in scored)
    return [json.loads(rows[index]["data"]) for index in order[:limit]]


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


def _type_clause(entity_type: str) -> tuple[str, tuple[str, ...]]:
    """SQL predicate + bind params matching every stored spelling of a type."""
    types = _expand_types(entity_type)
    return f"type IN ({','.join('?' * len(types))})", types


def _typed(query: str, *types: str) -> dict | None:
    types = _expand_types(*types)
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
    """Full-text search, re-ranked by the Rust relevance model.

    SQLite finds the candidates; `rank_entities` decides the order. bm25 over
    `search_text` cannot tell a name from a tag, so an exact-name hit used to
    land below an entity that merely mentioned the word. The scorer weights a
    name prefix at 1000 against a search-text mention at 120, which is the
    ordering a name lookup wants.
    """
    pool = _rank_pool(limit)
    try:
        rows = _BASE.fetchall(
            f"""SELECT {_RANK_COLUMNS} FROM entities e
               INNER JOIN (
                   SELECT id, rank FROM entities_fts WHERE entities_fts MATCH ?
                   ORDER BY rank
               ) fts ON e.id = fts.id
               LIMIT ?""",
            (query, pool),
        )
    except sqlite3.OperationalError:
        # No FTS5 index in this database (an old bake, or a build of SQLite
        # without the extension). LIKE finds the same rows unordered, which
        # makes re-ranking matter more here, not less.
        rows = _BASE.fetchall(
            "SELECT name, domains_text, search_text, data FROM entities "
            "WHERE lower(search_text) LIKE lower(?) LIMIT ?",
            (f"%{query}%", pool),
        )
    return _reranked(rows, query, limit)


def ByTradition(mythology: str, limit: int = 500) -> list[dict]:
    rows = _BASE.fetchall(
        "SELECT data FROM entities WHERE lower(mythology) = lower(?) LIMIT ?",
        (mythology, limit),
    )
    return _rows_data(rows)


ByCategory = ByTradition
ByMythology = ByTradition


def ByType(entity_type: str, mythology: str | None = None, limit: int = 500) -> list[dict]:
    clause, types = _type_clause(entity_type)
    if mythology:
        rows = _BASE.fetchall(
            f"SELECT data FROM entities WHERE {clause} AND lower(mythology) = lower(?) LIMIT ?",
            (*types, mythology, limit),
        )
    else:
        rows = _BASE.fetchall(
            f"SELECT data FROM entities WHERE {clause} LIMIT ?",
            (*types, limit),
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
        clause, types = _type_clause(entity_type)
        return _BASE.fetchone(
            f"SELECT COUNT(*) FROM entities WHERE {clause}", types
        )[0]
    return _BASE.fetchone("SELECT COUNT(*) FROM entities")[0]


def GetRandom(entity_type: str | None = None, mythology: str | None = None) -> dict | None:
    clause, types = _type_clause(entity_type) if entity_type else ("", ())
    if entity_type and mythology:
        row = _BASE.fetchone(
            f"SELECT data FROM entities WHERE {clause} AND lower(mythology)=lower(?) "
            "ORDER BY RANDOM() LIMIT 1",
            (*types, mythology),
        )
    elif entity_type:
        row = _BASE.fetchone(
            f"SELECT data FROM entities WHERE {clause} ORDER BY RANDOM() LIMIT 1",
            types,
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
    """Prefix search over names, re-ranked by the Rust relevance model."""
    pool = _rank_pool(limit)
    rows = []
    try:
        rows = _BASE.fetchall(
            f"""SELECT {_RANK_COLUMNS} FROM entities e
               INNER JOIN (
                   SELECT id, rank FROM entities_fts WHERE name MATCH ?
                   ORDER BY rank
               ) fts ON e.id = fts.id
               LIMIT ?""",
            (query + "*", pool),
        )
    except sqlite3.OperationalError:
        # Named, not blanket: this is the one recoverable condition here, a
        # database whose FTS table has no `name` column to prefix-match. Any
        # other error must reach the caller.
        rows = []
    if not rows:
        rows = _BASE.fetchall(
            "SELECT name, domains_text, search_text, data FROM entities "
            "WHERE lower(name) LIKE lower(?) LIMIT ?",
            (f"%{query}%", pool),
        )
    return _reranked(rows, query, limit)


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
    clause, types = _type_clause(entity_type) if entity_type else ("", ())
    if entity_type and mythology:
        rows = _BASE.fetchall(
            f"SELECT data FROM entities WHERE {clause} AND lower(mythology)=lower(?)",
            (*types, mythology),
        )
    elif entity_type:
        rows = _BASE.fetchall(f"SELECT data FROM entities WHERE {clause}", types)
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
