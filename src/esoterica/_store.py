"""Daily SQLite storage for scraped conspiracy content."""
from __future__ import annotations

import gzip
import shutil
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from eyecore import cache_dir, GRAPH_SCHEMA

ARTICLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id        TEXT PRIMARY KEY,
    url       TEXT UNIQUE NOT NULL,
    title     TEXT NOT NULL,
    source    TEXT,
    category  TEXT,
    published TEXT,
    summary   TEXT,
    content   TEXT,
    tags      TEXT,
    data      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source    ON articles(source);
CREATE INDEX IF NOT EXISTS idx_category  ON articles(category);
CREATE INDEX IF NOT EXISTS idx_published ON articles(published);
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    id UNINDEXED,
    title,
    summary,
    tags,
    tokenize='unicode61 remove_diacritics 1'
);
"""

# Full schema = articles + topic graph tables
SCHEMA = ARTICLES_SCHEMA + "\n" + GRAPH_SCHEMA


def data_dir() -> Path:
    """Platform-appropriate data directory for apocrypha daily DBs."""
    import os
    import platform
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "apocrypha"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _init_conn(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    for stmt in SCHEMA.strip().split(";"):
        s = stmt.strip()
        if s:
            db.execute(s)
    db.commit()
    return db


def today_db() -> sqlite3.Connection:
    """Open (or create) today's article DB."""
    return _init_conn(data_dir() / f"{date.today().isoformat()}.db")


def open_day(target: str | date) -> sqlite3.Connection:
    """Open a specific day's DB, decompressing from .gz if needed."""
    if isinstance(target, str):
        target = date.fromisoformat(target)
    d = data_dir()
    db_path = d / f"{target.isoformat()}.db"
    gz_path = db_path.with_suffix(".db.gz")

    if db_path.exists():
        return _init_conn(db_path)

    if gz_path.exists():
        with gzip.open(gz_path, "rb") as src, open(db_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return _init_conn(db_path)

    raise FileNotFoundError(f"No apocrypha data for {target}")


def available_days(include_compressed: bool = True) -> list[str]:
    """All available day keys (YYYY-MM-DD), most recent first."""
    d = data_dir()
    days: set[str] = {f.stem for f in d.glob("????-??-??.db")}
    if include_compressed:
        # .db.gz stems end in .db when using stem; handle double extension
        for gz in d.glob("????-??-??.db.gz"):
            days.add(gz.name[: -len(".db.gz")])
    return sorted(days, reverse=True)


def compress_old_days(keep_uncompressed: int = 2) -> list[str]:
    """Gzip daily DBs older than keep_uncompressed days. Returns compressed filenames."""
    cutoff = date.today() - timedelta(days=keep_uncompressed)
    compressed = []
    for db_file in data_dir().glob("????-??-??.db"):
        try:
            day = date.fromisoformat(db_file.stem)
        except ValueError:
            continue
        if day < cutoff:
            gz = db_file.with_suffix(".db.gz")
            with open(db_file, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
                shutil.copyfileobj(src, dst)
            db_file.unlink()
            compressed.append(gz.name)
    return compressed


def insert_articles(db: sqlite3.Connection, articles: list[dict]) -> int:
    """Bulk-insert articles, skipping duplicates. Returns new article count."""
    new = 0
    for a in articles:
        cur = db.execute(
            "INSERT OR IGNORE INTO articles"
            "(id, url, title, source, category, published, summary, content, tags, data) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                a["id"],
                a["url"],
                a["title"],
                a.get("source", ""),
                a.get("category", ""),
                a.get("published", ""),
                a.get("summary", ""),
                a.get("content", ""),
                a.get("tags", "[]"),
                a["data"],
            ),
        )
        if cur.rowcount:
            db.execute(
                "INSERT OR IGNORE INTO articles_fts(id, title, summary, tags) VALUES (?,?,?,?)",
                (
                    a["id"],
                    a["title"],
                    a.get("summary", ""),
                    a.get("tags", "[]"),
                ),
            )
            new += 1
    db.commit()
    return new
