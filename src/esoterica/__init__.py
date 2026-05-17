"""
esoterica — Conspiracy theories, hidden histories, and suppressed knowledge.

Quick start:
    import esoterica
    theory = esoterica.GetTheory("Illuminati")
    results = esoterica.Search("shadow government")
    orgs = esoterica.ByCategory("government")
"""
from __future__ import annotations

try:
    from ._core import score_entity, tags_match
    _RUST_CORE = True
except ImportError:
    _RUST_CORE = False

    def score_entity(name: str, description: str, search_text: str, query: str) -> float:
        q = query.lower()
        n = name.lower()
        if not q:
            return 0.0
        score = 0.0
        if n.startswith(q):
            score += 1000.0
        elif q in n:
            score += 500.0
        if q in description.lower():
            score += 150.0
        if q in search_text.lower():
            score += 120.0
        return score

    def tags_match(tags: list, query: str) -> bool:
        q = query.lower()
        return any(t.lower().startswith(q) or q in t.lower() for t in tags)

from ._query import (
    Get,
    Search,
    ByCategory,
    ByType,
    Count,
    GetRandom,
    GetFuzzy,
    GetMost,
    GetAll,
    GetTopics,
    GetRelated,
    GetTopicTree,
    SearchCorpus,
    FetchCorpus,
    ListCorpuses,
    _typed,
)

from ._scraper import (
    add_feed as AddFeed,
    remove_feed as RemoveFeed,
    scrape_all as Scrape,
    load_sources as ListSources,
    add_reddit_sub as AddSubreddit,
)

from ._store import (
    available_days as AvailableDays,
    compress_old_days as Compress,
    data_dir as DataDir,
)

from ._llm_categorizer import (
    categorize_batch as Categorize,
    generate_daily_report as DailyReport,
)


def GetTheory(query: str) -> dict | None:
    """Return a conspiracy theory by name."""
    return _typed(query, "theory")


def GetEvent(query: str) -> dict | None:
    """Return an event by name."""
    return _typed(query, "event")


def GetFigure(query: str) -> dict | None:
    """Return a figure by name."""
    return _typed(query, "figure")


def GetOrganization(query: str) -> dict | None:
    """Return an organization by name."""
    return _typed(query, "organization")


def GetConcept(query: str) -> dict | None:
    """Return a concept by name."""
    return _typed(query, "concept")


def GetDocument(query: str) -> dict | None:
    """Return a document by name."""
    return _typed(query, "document")


__version__ = "1.0.0"

__all__ = [
    # Core query
    "Get",
    "GetTheory",
    "GetEvent",
    "GetFigure",
    "GetOrganization",
    "GetConcept",
    "GetDocument",
    "Search",
    "ByCategory",
    "ByType",
    "Count",
    "GetRandom",
    "GetFuzzy",
    "GetMost",
    "GetAll",
    # Topic graph
    "GetTopics",
    "GetRelated",
    "GetTopicTree",
    # Corpus
    "SearchCorpus",
    "FetchCorpus",
    "ListCorpuses",
    # Scraper
    "AddFeed",
    "RemoveFeed",
    "Scrape",
    "ListSources",
    "AddSubreddit",
    # Store
    "AvailableDays",
    "Compress",
    "DataDir",
    # LLM
    "Categorize",
    "DailyReport",
    "_RUST_CORE",
]
