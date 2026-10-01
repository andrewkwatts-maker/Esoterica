"""
esoterica -- Magic systems, spells, rituals, arcane traditions, and esoteric knowledge.

Quick start:
    import esoterica
    spell     = esoterica.GetSpell("Fireball")
    ritual    = esoterica.GetRitual("summoning")
    tradition = esoterica.GetTradition("Hermeticism")
    results   = esoterica.Search("banishment")
    spells    = esoterica.ByTradition("ceremonial-magic")
    esoterica.FetchCorpus("gutenberg-key-of-solomon")
    hits      = esoterica.SearchCorpus("circle of protection")

Backend
-------
The text normalisation and relevance ranking are implemented in the Rust crate
``apocrypha_core`` and reach Python through the compiled extension
``esoterica._core``. There is no Python re-implementation to fall back to: if
the extension is missing, the accelerated symbols raise
:class:`RustBackendUnavailable` naming the reason, and the SQLite-backed
lookups that do not need it keep working.

Call :func:`assert_rust_backend` at startup to fail fast when the accelerated
path is required, or :func:`backend_report` to see what is actually loaded --
including whether a stale extension from an earlier build is shadowing the
current one.

What is Rust and what is not
----------------------------
Rust owns the loop-heavy work: HTML-to-plaintext normalisation
(:func:`strip_html`, :func:`strip_html_batch`) and entity scoring and ranking
(:func:`score_entity`, :func:`tags_match`, :func:`is_subsequence`,
:func:`rank_entities`). SQL, HTTP, feed parsing, configuration and
orchestration stay in Python, where the time goes to the network and to SQLite
rather than to the interpreter.
"""
from __future__ import annotations

from ._backend import (
    HAS_RUST,
    RustBackendUnavailable,
    assert_rust_backend,
    backend_report,
    is_rust_backend,
    is_subsequence,
    rank_entities,
    score_entity,
    strip_html,
    strip_html_batch,
    tags_match,
    version_rust,
)

#: Historical spelling of :data:`HAS_RUST`, kept because it was exported in
#: ``__all__`` from the first release. It no longer selects between two
#: implementations -- there is only one -- but it still answers "is the
#: extension loaded".
_RUST_CORE = HAS_RUST

from ._query import (
    Get,
    Search,
    Refresh,
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
    """Return a magical tradition or system by name.

    Spans the `tradition` and `magic` types: the baked corpus stores its 106
    magic systems as `magic`, the spelling their source documents declare.
    """
    return _typed(query, "tradition")


def GetGrimoire(query: str) -> dict | None:
    """Return a grimoire or magical text by name."""
    return _typed(query, "grimoire")


def GetIngredient(query: str) -> dict | None:
    """Return a magical ingredient or component by name.

    Spans the `ingredient` and `herb` types: the baked corpus stores all 127
    of its components as `herb`, the spelling their source documents declare.
    """
    return _typed(query, "ingredient")


def GetHerb(query: str) -> dict | None:
    """Return a magical herb or plant by name."""
    return _typed(query, "herb")


def GetArtifact(query: str) -> dict | None:
    """Return a magical artifact or object by name."""
    return _typed(query, "artifact")


def GetPractitioner(query: str) -> dict | None:
    """Return a notable practitioner or mage by name."""
    return _typed(query, "practitioner")


__version__ = "1.2.0"

__all__ = [
    # Core query
    "Get",
    "GetSpell",
    "GetRitual",
    "GetTradition",
    "GetGrimoire",
    "GetIngredient",
    "GetHerb",
    "GetArtifact",
    "GetPractitioner",
    "Search",
    "Refresh",
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
    # Rust backend
    "HAS_RUST",
    "_RUST_CORE",
    "RustBackendUnavailable",
    "assert_rust_backend",
    "backend_report",
    "is_rust_backend",
    "version_rust",
    "score_entity",
    "tags_match",
    "is_subsequence",
    "rank_entities",
    "strip_html",
    "strip_html_batch",
]
