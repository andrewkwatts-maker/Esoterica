"""Shared fixtures for esoterica tests.

Strategy: patch esoterica._query._BASE with a MagicMock whose fetchone/fetchall/execute
side-effects delegate to a real in-memory SQLite connection containing the full schema
and a small set of known magic entities.
"""
import json
import sqlite3

import pytest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Schema constants (mirrors what bake.py produces)
# ---------------------------------------------------------------------------

GRAPH_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    parent_id TEXT REFERENCES topics(id),
    description TEXT,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_topics_name ON topics(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_id);
CREATE INDEX IF NOT EXISTS idx_topics_type ON topics(type);

CREATE TABLE IF NOT EXISTS topic_links (
    from_id TEXT NOT NULL REFERENCES topics(id),
    to_id TEXT NOT NULL REFERENCES topics(id),
    relation TEXT NOT NULL DEFAULT 'related',
    weight REAL DEFAULT 1.0,
    PRIMARY KEY (from_id, to_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_links_from ON topic_links(from_id);
CREATE INDEX IF NOT EXISTS idx_links_to ON topic_links(to_id);
"""

ENTITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    mythology TEXT,
    domains_text TEXT,
    search_text TEXT,
    data TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id UNINDEXED, search_text, tokenize='unicode61 remove_diacritics 1'
);
CREATE TABLE IF NOT EXISTS entity_topics (
    entity_id TEXT,
    topic_id TEXT,
    PRIMARY KEY (entity_id, topic_id)
);
"""

# ---------------------------------------------------------------------------
# Test fixture data  (mythology column stores the magic tradition)
# ---------------------------------------------------------------------------

HERMETICISM = {
    "id": "hermeticism",
    "name": "Hermeticism",
    "type": "tradition",
    "mythology": "western-esoteric",
    "domains": "sacred geometry kabbalah alchemy thoth",
}
FIREBALL = {
    "id": "fireball",
    "name": "Fireball",
    "type": "spell",
    "mythology": "elemental-magic",
    "domains": "fire destruction evocation attack",
}
LBRP = {
    "id": "lbrp",
    "name": "Lesser Banishing Ritual",
    "type": "ritual",
    "mythology": "ceremonial-magic",
    "domains": "banishment protection purification circle",
}
CROWLEY = {
    "id": "crowley",
    "name": "Aleister Crowley",
    "type": "practitioner",
    "mythology": "thelema",
    "domains": "ritual magic occult thelema golden dawn",
}
KEY_OF_SOLOMON = {
    "id": "key-of-solomon",
    "name": "The Key of Solomon",
    "type": "grimoire",
    "mythology": "ceremonial-magic",
    "domains": "demons spirits conjuration seals",
}

ALL_ENTITIES = [HERMETICISM, FIREBALL, LBRP, CROWLEY, KEY_OF_SOLOMON]


# ---------------------------------------------------------------------------
# DB builder
# ---------------------------------------------------------------------------

def make_test_db(entities: list[dict]) -> sqlite3.Connection:
    """Create an in-memory SQLite DB with the full esoterica schema and insert entities."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    for stmt in (GRAPH_SCHEMA + ENTITY_SCHEMA).strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)

    for e in entities:
        conn.execute(
            "INSERT OR REPLACE INTO entities"
            "(id, name, type, mythology, domains_text, search_text, data)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                e["id"],
                e["name"],
                e["type"],
                e.get("mythology", ""),
                e.get("domains", ""),
                e.get("name", ""),
                json.dumps(e),
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO entities_fts(id, search_text) VALUES (?, ?)",
            (e["id"], e.get("name", "")),
        )

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Return a fresh in-memory SQLite connection loaded with ALL_ENTITIES."""
    return make_test_db(ALL_ENTITIES)


@pytest.fixture
def patch_base(db):
    """Patch esoterica._query._BASE so all queries run against the in-memory test DB."""
    with patch("esoterica._query._BASE") as mock_base:
        mock_base.conn = db
        mock_base.fetchone.side_effect = lambda sql, params=(): db.execute(sql, params).fetchone()
        mock_base.fetchall.side_effect = lambda sql, params=(): db.execute(sql, params).fetchall()
        mock_base.execute.side_effect = lambda sql, params=(): db.execute(sql, params)
        yield mock_base
