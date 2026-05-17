"""
esoterica — Magic systems, spells, rituals, arcane traditions, and esoteric knowledge.

Quick start:
    import esoterica
    spell     = esoterica.GetSpell("Fireball")
    ritual    = esoterica.GetRitual("summoning")
    tradition = esoterica.GetTradition("Hermeticism")
    results   = esoterica.Search("banishment")
    spells    = esoterica.ByTradition("ceremonial-magic")
    esoterica.FetchCorpus("gutenberg-key-of-solomon")
    hits      = esoterica.SearchCorpus("circle of protection")
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
    ByTradition,
    ByCategory,
    ByMythology,
    ByType,
    AllSpells,
    AllRituals,
    AllTraditions,
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


def GetSpell(query: str) -> dict | None:
    """Return a spell or incantation by name or effect."""
    return _typed(query, "spell")


def GetRitual(query: str) -> dict | None:
    """Return a ritual or ceremony by name."""
    return _typed(query, "ritual")


def GetTradition(query: str) -> dict | None:
    """Return a magical tradition or system by name."""
    return _typed(query, "tradition")


def GetGrimoire(query: str) -> dict | None:
    """Return a grimoire or magical text by name."""
    return _typed(query, "grimoire")


def GetIngredient(query: str) -> dict | None:
    """Return a magical ingredient or component by name."""
    return _typed(query, "ingredient")


def GetArtifact(query: str) -> dict | None:
    """Return a magical artifact or object by name."""
    return _typed(query, "artifact")


def GetPractitioner(query: str) -> dict | None:
    """Return a notable practitioner or mage by name."""
    return _typed(query, "practitioner")


__version__ = "1.0.1"

__all__ = [
    # Core query
    "Get",
    "GetSpell",
    "GetRitual",
    "GetTradition",
    "GetGrimoire",
    "GetIngredient",
    "GetArtifact",
    "GetPractitioner",
    "Search",
    "ByTradition",
    "ByCategory",
    "ByMythology",
    "ByType",
    "AllSpells",
    "AllRituals",
    "AllTraditions",
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
    # Live / user-contributed
    "AddFeed",
    "RemoveFeed",
    "Scrape",
    "ListSources",
    "AddSubreddit",
    "AvailableDays",
    "Compress",
    "DataDir",
    "Categorize",
    "DailyReport",
    "_RUST_CORE",
]
