#!/usr/bin/env python3
"""Bake magic-systems data into esoterica.db (SQLite) via the Firestore REST API.

Usage:
    python scripts/bake.py                          # pull from Firebase
    python scripts/bake.py --source /path/to/dir   # use local JSON export
    python scripts/bake.py --api-key KEY            # override API key
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Install bake deps: pip install 'esoterica[bake]'")

try:
    from eyecore import compress_db, GRAPH_SCHEMA
except ImportError:
    sys.exit("eyecore not installed. Run: pip install eyecore")

ROOT = Path(__file__).parent.parent
DATA_OUT = ROOT / "src" / "esoterica" / "_data" / "esoterica.db"

PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
DEFAULT_API_KEY = os.getenv("FIREBASE_API_KEY", "")
_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

COLLECTIONS: dict[str, str] = {
    "spells": "spell",
    "rituals": "ritual",
    "magic": "tradition",       # legacy collection name from azrael split
    "traditions": "tradition",
    "grimoires": "grimoire",
    "herbs": "ingredient",      # legacy collection name from azrael split
    "ingredients": "ingredient",
    "artifacts": "artifact",
    "practitioners": "practitioner",
}

TYPE_FIXES: dict[str, str] = {}

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    mythology TEXT,
    domains_text TEXT,
    search_text TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_name ON entities(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_mythology ON entities(mythology COLLATE NOCASE);
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id UNINDEXED,
    search_text,
    tokenize='unicode61 remove_diacritics 1'
);

CREATE TABLE IF NOT EXISTS entity_topics (
    entity_id  TEXT NOT NULL REFERENCES entities(id),
    topic_id   TEXT NOT NULL REFERENCES topics(id),
    weight     REAL DEFAULT 1.0,
    PRIMARY KEY (entity_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_entity_topics_entity ON entity_topics(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_topics_topic  ON entity_topics(topic_id);
"""


# ── Firestore REST helpers ────────────────────────────────────────────────────

def _parse_value(val: dict):
    if "stringValue" in val:
        return val["stringValue"]
    if "integerValue" in val:
        return int(val["integerValue"])
    if "doubleValue" in val:
        return float(val["doubleValue"])
    if "booleanValue" in val:
        return val["booleanValue"]
    if "nullValue" in val:
        return None
    if "timestampValue" in val:
        return val["timestampValue"]
    if "arrayValue" in val:
        return [_parse_value(v) for v in val["arrayValue"].get("values", [])]
    if "mapValue" in val:
        return {k: _parse_value(v) for k, v in val["mapValue"].get("fields", {}).items()}
    return None


def _doc_to_dict(doc: dict) -> dict:
    result = {k: _parse_value(v) for k, v in doc.get("fields", {}).items()}
    result["id"] = doc["name"].rsplit("/", 1)[-1]
    return result


def _fetch_collection(session: requests.Session, collection: str, api_key: str) -> list[dict]:
    url = f"{_BASE}/{collection}"
    docs: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict = {"key": api_key, "pageSize": 300}
        if page_token:
            params["pageToken"] = page_token
        for attempt in range(5):
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                import time
                wait = 2 ** attempt
                print(f"(rate limited, waiting {wait}s)", end=" ", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
        for doc in data.get("documents", []):
            docs.append(_doc_to_dict(doc))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return docs


# ── DB helpers ────────────────────────────────────────────────────────────────

def _coerce_type(raw: str | None, fallback: str) -> str:
    if not raw:
        return fallback
    return TYPE_FIXES.get(raw, raw)


def _str_list(val) -> str:
    if not val:
        return ""
    if isinstance(val, list):
        return " ".join(str(v) for v in val if v)
    return str(val)


def _first_str(*candidates) -> str | None:
    for c in candidates:
        if isinstance(c, str) and c:
            return c
    return None


def _safe_str(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        return _str_list(val)
    return ""


def _domains_text(e: dict) -> str:
    parts = [
        _str_list(e.get("domains")),
        _str_list(e.get("abilities")),
        _str_list(e.get("powers")),
        _str_list(e.get("attributes")),
        _str_list(e.get("significance")),
        _str_list(e.get("tags")),
    ]
    return " ".join(p for p in parts if p).lower()


def _search_text(e: dict) -> str:
    desc = e.get("description") or e.get("shortDescription") or e.get("longDescription") or ""
    parts = [
        _safe_str(e.get("name", "")),
        _safe_str(e.get("category") or e.get("mythology") or ""),
        _safe_str(desc),
        _str_list(e.get("domains")),
        _str_list(e.get("tags")),
        _str_list(e.get("aliases")),
        _safe_str(e.get("subtitle", "")),
    ]
    return " ".join(p for p in parts if p)


def _init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(str(db_path))
    # Execute GRAPH_SCHEMA first so topics/topic_links tables exist
    # before entity_topics references them
    for stmt in GRAPH_SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            db.execute(s)
    for stmt in CREATE_SQL.strip().split(";"):
        s = stmt.strip()
        if s:
            db.execute(s)
    db.commit()
    return db


def _insert_batch(db: sqlite3.Connection, rows: list, fts_rows: list) -> None:
    db.executemany(
        "INSERT OR REPLACE INTO entities"
        "(id, name, type, mythology, domains_text, search_text, data) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    db.executemany(
        "INSERT INTO entities_fts(id, search_text) VALUES (?,?)",
        fts_rows,
    )
    db.commit()


def _build_topic_graph(db: sqlite3.Connection, all_rows: list[dict]) -> None:
    """Populate the topics table and entity_topics links from baked entity data."""
    from eyecore import TopicGraph

    graph = TopicGraph(db)

    # Collect unique category/mythology values as top-level topics
    categories: dict[str, str] = {}  # normalized_name -> display_name
    for e in all_rows:
        cat = e.get("category") or e.get("mythology")
        if cat and isinstance(cat, str):
            key = cat.strip().lower()
            if key and key not in categories:
                categories[key] = cat.strip()

    # Upsert one root topic per category
    for key, display in categories.items():
        topic_id = f"cat:{key}"
        graph.upsert_topic(
            id=topic_id,
            name=display,
            type="category",
            description=f"Conspiracy category: {display}",
        )

    # Collect unique tags as child topics and build entity_topic links
    entity_topic_rows: list[tuple] = []

    for e in all_rows:
        eid = e.get("id")
        if not eid:
            continue

        cat = e.get("category") or e.get("mythology")
        if cat and isinstance(cat, str):
            cat_id = f"cat:{cat.strip().lower()}"
            entity_topic_rows.append((eid, cat_id, 1.0))

        tags = e.get("tags") or e.get("domains") or []
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                continue
            tag_key = tag.strip().lower()
            tag_id = f"tag:{tag_key}"
            # Upsert the tag topic under its category if known
            parent_id = f"cat:{cat.strip().lower()}" if cat else None
            graph.upsert_topic(
                id=tag_id,
                name=tag.strip(),
                type="tag",
                parent_id=parent_id,
            )
            entity_topic_rows.append((eid, tag_id, 0.8))

    graph.commit()

    # Bulk-insert entity_topics (ignore duplicates)
    db.executemany(
        "INSERT OR IGNORE INTO entity_topics(entity_id, topic_id, weight) VALUES (?,?,?)",
        entity_topic_rows,
    )
    db.commit()
    print(f"  Topic graph: {len(categories)} categories, {len(entity_topic_rows)} entity-topic links")


# ── Bake functions ────────────────────────────────────────────────────────────

def bake_from_firebase(db_path: Path, api_key: str) -> None:
    session = requests.Session()
    db = _init_db(db_path)
    total = 0
    all_entities: list[dict] = []
    for col_name, entity_type in COLLECTIONS.items():
        print(f"  {col_name}...", end=" ", flush=True)
        try:
            entities = _fetch_collection(session, col_name, api_key)
        except requests.HTTPError as exc:
            print(f"SKIP ({exc.response.status_code})")
            continue
        rows, fts_rows = [], []
        for e in entities:
            eid = _first_str(e.get("id")) or ""
            if not eid:
                continue
            etype = _coerce_type(_first_str(e.get("type")), entity_type)
            e["type"] = etype
            category = _first_str(e.get("category"), e.get("mythology"))
            name = _first_str(e.get("name")) or eid
            srch = _search_text(e)
            rows.append((eid, name, etype, category, _domains_text(e), srch,
                         json.dumps(e, ensure_ascii=False)))
            fts_rows.append((eid, srch))
            all_entities.append(e)
        _insert_batch(db, rows, fts_rows)
        print(len(rows))
        total += len(rows)
    print(f"\nBuilding topic graph...")
    _build_topic_graph(db, all_entities)
    size = db_path.stat().st_size / 1_048_576
    print(f"\nDone: {total} entities -> {db_path} ({size:.1f} MB)")
    db.close()
    gz = compress_db(db_path)
    print(f"Compressed -> {gz} ({gz.stat().st_size / 1_048_576:.1f} MB)")


def bake_from_local(source_dir: Path, db_path: Path) -> None:
    if not source_dir.exists():
        sys.exit(f"Source not found: {source_dir}")
    db = _init_db(db_path)
    total = 0
    all_entities: list[dict] = []
    for col_name, entity_type in COLLECTIONS.items():
        col_dir = source_dir / col_name
        if not col_dir.exists():
            print(f"  SKIP {col_name} (not found)")
            continue
        files = [f for f in col_dir.glob("*.json") if not f.name.startswith("_")]
        print(f"  {col_name}: {len(files)} -> {entity_type}")
        rows, fts_rows = [], []
        for jf in files:
            try:
                e = json.loads(jf.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(e, dict):
                continue
            eid = e.get("id") or jf.stem
            e["id"] = eid
            etype = _coerce_type(e.get("type"), entity_type)
            e["type"] = etype
            category = _first_str(e.get("category"), e.get("mythology"))
            name = _first_str(e.get("name")) or eid
            srch = _search_text(e)
            rows.append((eid, name, etype, category, _domains_text(e), srch,
                         json.dumps(e, ensure_ascii=False)))
            fts_rows.append((eid, srch))
            all_entities.append(e)
        _insert_batch(db, rows, fts_rows)
        total += len(rows)
    print(f"\nBuilding topic graph...")
    _build_topic_graph(db, all_entities)
    size = db_path.stat().st_size / 1_048_576
    print(f"\nDone: {total} entities -> {db_path} ({size:.1f} MB)")
    db.close()
    gz = compress_db(db_path)
    print(f"Compressed -> {gz} ({gz.stat().st_size / 1_048_576:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bake conspiracy data into apocrypha.db")
    parser.add_argument("--source", metavar="DIR", help="Local JSON export directory (skips Firebase)")
    parser.add_argument("--api-key", default=os.getenv("FIREBASE_API_KEY", DEFAULT_API_KEY),
                        metavar="KEY", help="Firebase public API key")
    parser.add_argument("--out", default=str(DATA_OUT), metavar="PATH",
                        help=f"Output path (default: {DATA_OUT})")
    args = parser.parse_args()
    out = Path(args.out)
    if args.source:
        bake_from_local(Path(args.source), out)
    else:
        bake_from_firebase(out, args.api_key)


if __name__ == "__main__":
    main()
