"""The Rust relevance model and the re-ranking `_query` wraps around it.

`Search()` and `GetFuzzy()` let SQLite pick the candidates and let
`rank_entities` decide the order. bm25 over `search_text` cannot tell a name
from a tag, so an exact-name hit used to land below an entity that merely
mentioned the word. These tests hold the two properties that fix depends on:
the scorer's ordering, and the rule that re-ranking may reorder but never
lose a row the database found.
"""
from __future__ import annotations

import json

import pytest

import esoterica
from esoterica._query import _RANK_POOL_CAP, _rank_pool, _reranked


def _row(name: str, domains: str = "", search: str = "") -> dict:
    """A stand-in for the sqlite3.Row that `_reranked` consumes."""
    payload = {"name": name, "domains_text": domains, "search_text": search}
    return {**payload, "data": json.dumps(payload)}


# ---------------------------------------------------------------------------
# The scorer itself
# ---------------------------------------------------------------------------

def test_a_name_prefix_outranks_a_search_text_mention():
    ranked = esoterica.rank_entities(
        [
            ("Hermeticism", "", "fire is mentioned here"),
            ("Fireball", "", ""),
        ],
        "fire",
        20,
    )
    assert [index for index, _score in ranked] == [1, 0]


def test_an_empty_query_scores_zero_rather_than_matching_everything():
    assert esoterica.score_entity("Fireball", "", "", "") == 0.0
    assert esoterica.rank_entities([("Fireball", "", "")], "", 20) == []


def test_a_zero_limit_raises_instead_of_silently_returning_nothing():
    """The bound is refused at the boundary, not turned into an empty result."""
    with pytest.raises(ValueError):
        esoterica.rank_entities([("Fireball", "", "")], "fire", 0)


def test_over_long_text_raises_rather_than_being_truncated():
    huge = "a" * (esoterica._backend.MAX_TEXT_BYTES + 1)
    with pytest.raises(OverflowError):
        esoterica.strip_html(huge)


# ---------------------------------------------------------------------------
# The wrapper around it
# ---------------------------------------------------------------------------

def test_reranking_reorders_but_never_loses_a_row():
    """A row the scorer cannot score is kept, in its original position order.

    The FTS tokenizer folds diacritics and matches whole tokens, so it finds
    rows a substring scorer legitimately cannot. Dropping those would be a
    silent regression against the SQL-only behaviour this replaced.
    """
    rows = [
        _row("Unrelated Entity"),
        _row("Fireball"),
        _row("Another Unrelated"),
    ]
    out = _reranked(rows, "fire", 10)
    assert len(out) == len(rows), "re-ranking lost a row the database found"
    assert out[0]["name"] == "Fireball"
    assert [entry["name"] for entry in out[1:]] == [
        "Unrelated Entity",
        "Another Unrelated",
    ]


def test_reranking_cuts_to_the_limit():
    rows = [_row(f"Fire {n}") for n in range(10)]
    assert len(_reranked(rows, "fire", 3)) == 3


def test_reranking_leaves_sql_semantics_alone_for_a_non_positive_limit():
    """A negative LIMIT means "no limit" in SQL; ranking must not redefine it."""
    rows = [_row("Fireball"), _row("Unrelated")]
    out = _reranked(rows, "fire", -1)
    assert [entry["name"] for entry in out] == ["Fireball", "Unrelated"]


def test_an_empty_query_skips_ranking_entirely():
    rows = [_row("Fireball"), _row("Unrelated")]
    assert [entry["name"] for entry in _reranked(rows, "", 10)] == [
        "Fireball",
        "Unrelated",
    ]


def test_the_candidate_pool_is_wider_than_the_page_but_bounded():
    """Wide enough to see rows the SQL order would have cut off, and no wider.

    Above the cap the pool is the caller's own limit: a page may never be
    served from fewer candidates than it asks for, so the cap widens the
    window rather than narrowing the answer.
    """
    assert _rank_pool(20) > 20, "a pool no wider than the page cannot re-rank"
    assert _rank_pool(20) <= _RANK_POOL_CAP
    assert _rank_pool(10_000) == 10_000
    assert _rank_pool(0) == 0
    assert _rank_pool(-1) == -1
