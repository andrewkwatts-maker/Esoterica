"""
esoterica — Conspiracy theories, hidden histories, and suppressed knowledge.

Quick start:
    import esoterica
    theory = esoterica.GetTheory("Illuminati")
    results = esoterica.Search("shadow government")
    orgs = esoterica.ByCategory("government")
"""
from __future__ import annotations

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


__version__ = "1.0.0a0"

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
]
