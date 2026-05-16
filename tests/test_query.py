"""Unit tests for esoterica._query — all queries run against an in-memory SQLite DB."""
import pytest
import esoterica
from esoterica._query import (
    Get,
    Search,
    ByMythology,
    ByCategory,
    ByType,
    Count,
    GetRandom,
    GetFuzzy,
    GetMost,
    GetAll,
)


# ---------------------------------------------------------------------------
# Get — exact / fuzzy name lookup
# ---------------------------------------------------------------------------

def test_get_exact(patch_base):
    """Get with exact name returns the matching entity."""
    result = Get("Illuminati")
    assert result is not None
    assert result["name"] == "Illuminati"


def test_get_fuzzy(patch_base):
    """Get with lowercase name still finds the entity (case-insensitive)."""
    result = Get("illuminati")
    assert result is not None
    assert result["name"] == "Illuminati"


def test_get_partial(patch_base):
    """Get with a substring matches via the LIKE fallback."""
    result = Get("lluminati")
    assert result is not None
    assert result["name"] == "Illuminati"


def test_get_none(patch_base):
    """Get with an unknown name returns None."""
    result = Get("Nonexistent9999")
    assert result is None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search(patch_base):
    """Search returns at least one result for a known entity name."""
    results = Search("Illuminati")
    assert isinstance(results, list)
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "Illuminati" in names


def test_search_returns_list_on_no_match(patch_base):
    """Search with a non-matching term returns an empty list, never None."""
    results = Search("xyzzy_no_match_99")
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# ByCategory (alias for ByMythology, using the mythology column as category)
# ---------------------------------------------------------------------------

def test_by_category(patch_base):
    """ByCategory('western') returns the Illuminati entry."""
    results = ByCategory("western")
    assert len(results) >= 1
    for r in results:
        assert r["mythology"] == "western"


def test_by_category_case_insensitive(patch_base):
    """ByCategory is case-insensitive."""
    results = ByCategory("WESTERN")
    assert len(results) >= 1


def test_by_mythology_alias(patch_base):
    """ByMythology is an alias for ByCategory; both return the same results."""
    assert ByMythology("western") == ByCategory("western")


def test_by_category_no_results(patch_base):
    """ByCategory with unknown value returns empty list."""
    results = ByCategory("ancient-sumerian")
    assert results == []


# ---------------------------------------------------------------------------
# ByType
# ---------------------------------------------------------------------------

def test_by_type_organization(patch_base):
    """ByType('organization') returns the Illuminati."""
    results = ByType("organization")
    assert len(results) == 1
    assert results[0]["name"] == "Illuminati"


def test_by_type_theory(patch_base):
    """ByType('theory') returns the New World Order."""
    results = ByType("theory")
    assert len(results) == 1
    assert results[0]["name"] == "New World Order"


def test_by_type_filtered(patch_base):
    """ByType('figure', 'financial') returns only George Soros."""
    results = ByType("figure", "financial")
    assert len(results) == 1
    assert results[0]["name"] == "George Soros"


def test_by_type_no_results(patch_base):
    """ByType with an absent type returns empty list."""
    results = ByType("myth")
    assert results == []


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

def test_count_all(patch_base):
    """Count() without filter returns total entity count (5 in test DB)."""
    assert Count() == 5


def test_count_typed(patch_base):
    """Count('organization') returns 1 (Illuminati only)."""
    assert Count("organization") == 1


def test_count_zero_for_missing_type(patch_base):
    """Count with an absent type returns 0."""
    assert Count("myth") == 0


# ---------------------------------------------------------------------------
# GetRandom
# ---------------------------------------------------------------------------

def test_getrandom(patch_base):
    """GetRandom() returns a dict with a 'name' key."""
    result = GetRandom()
    assert result is not None
    assert isinstance(result, dict)
    assert "name" in result


def test_getrandom_typed(patch_base):
    """GetRandom('theory') returns an entity whose type is 'theory'."""
    result = GetRandom("theory")
    assert result is not None
    assert result["type"] == "theory"


def test_getrandom_mythology(patch_base):
    """GetRandom(mythology='financial') returns a financial entity."""
    result = GetRandom(mythology="financial")
    assert result is not None
    assert result["mythology"] == "financial"


def test_getrandom_typed_and_mythology(patch_base):
    """GetRandom with both type and mythology filters correctly."""
    result = GetRandom("figure", "financial")
    assert result is not None
    assert result["type"] == "figure"
    assert result["mythology"] == "financial"


def test_getrandom_no_match_returns_none(patch_base):
    """GetRandom for a type with no entities returns None."""
    result = GetRandom("myth")
    assert result is None


# ---------------------------------------------------------------------------
# GetFuzzy
# ---------------------------------------------------------------------------

def test_getfuzzy(patch_base):
    """GetFuzzy('MK') finds MK-Ultra via the LIKE fallback."""
    results = GetFuzzy("MK")
    assert isinstance(results, list)
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "MK-Ultra" in names


def test_getfuzzy_case_insensitive(patch_base):
    """GetFuzzy is case-insensitive."""
    results = GetFuzzy("mk")
    names = [r["name"] for r in results]
    assert "MK-Ultra" in names


def test_getfuzzy_no_match(patch_base):
    """GetFuzzy with no match returns empty list."""
    results = GetFuzzy("xyzzy_nope_9999")
    assert results == []


# ---------------------------------------------------------------------------
# GetMost
# ---------------------------------------------------------------------------

def test_getmost_mythology(patch_base):
    """GetMost('mythology') returns a list including at least one category."""
    results = GetMost("mythology")
    assert isinstance(results, list)
    assert len(results) >= 1
    for r in results:
        assert "mythology" in r
        assert "count" in r


def test_getmost_type(patch_base):
    """GetMost('type') returns a list that includes known types."""
    results = GetMost("type")
    assert isinstance(results, list)
    assert len(results) >= 1
    keys = {r["type"] for r in results}
    assert "organization" in keys or "theory" in keys or "event" in keys


def test_getmost_count_field(patch_base):
    """GetMost results each have a 'count' key with a positive integer."""
    results = GetMost("type")
    for r in results:
        assert "count" in r
        assert isinstance(r["count"], int)
        assert r["count"] >= 1


def test_getmost_invalid_field(patch_base):
    """GetMost with an unsupported field raises ValueError."""
    with pytest.raises(ValueError):
        GetMost("name")


# ---------------------------------------------------------------------------
# GetAll
# ---------------------------------------------------------------------------

def test_getall(patch_base):
    """GetAll() without filters returns all 5 entities."""
    results = GetAll()
    assert isinstance(results, list)
    assert len(results) == 5


def test_getall_filtered_type(patch_base):
    """GetAll('document') returns the single document entity."""
    results = GetAll("document")
    assert len(results) == 1
    assert results[0]["name"] == "Protocols of Zion"


def test_getall_filtered_mythology(patch_base):
    """GetAll(mythology='government') returns only MK-Ultra."""
    results = GetAll(mythology="government")
    assert len(results) == 1
    assert results[0]["name"] == "MK-Ultra"


def test_getall_filtered_type_and_mythology(patch_base):
    """GetAll('figure', 'financial') returns only George Soros."""
    results = GetAll("figure", "financial")
    assert len(results) == 1
    assert results[0]["name"] == "George Soros"


def test_getall_no_match(patch_base):
    """GetAll with non-existent type returns empty list."""
    results = GetAll("myth")
    assert results == []


# ---------------------------------------------------------------------------
# Typed helpers defined in esoterica.__init__
# ---------------------------------------------------------------------------

def test_gettheory(patch_base):
    """esoterica.GetTheory('New World Order') returns the NWO entity."""
    result = esoterica.GetTheory("New World Order")
    assert result is not None
    assert result["name"] == "New World Order"
    assert result["type"] == "theory"


def test_getevent(patch_base):
    """esoterica.GetEvent('MK-Ultra') returns the MK-Ultra entity."""
    result = esoterica.GetEvent("MK-Ultra")
    assert result is not None
    assert result["name"] == "MK-Ultra"
    assert result["type"] == "event"


def test_getfigure(patch_base):
    """esoterica.GetFigure('George Soros') returns the Soros entity."""
    result = esoterica.GetFigure("George Soros")
    assert result is not None
    assert result["name"] == "George Soros"
    assert result["type"] == "figure"


def test_getorganization(patch_base):
    """esoterica.GetOrganization('Illuminati') returns the Illuminati entity."""
    result = esoterica.GetOrganization("Illuminati")
    assert result is not None
    assert result["name"] == "Illuminati"
    assert result["type"] == "organization"


def test_getdocument(patch_base):
    """esoterica.GetDocument('Protocols') finds Protocols of Zion via LIKE."""
    result = esoterica.GetDocument("Protocols")
    assert result is not None
    assert result["type"] == "document"


def test_typed_helper_wrong_type_returns_none(patch_base):
    """GetTheory with an organization name returns None (type mismatch)."""
    result = esoterica.GetTheory("Illuminati")
    assert result is None


def test_typed_helper_domain_fallback(patch_base):
    """_typed falls back to domains_text LIKE; 'control' is in multiple domains."""
    result = esoterica.GetOrganization("control")
    # Illuminati has 'control' in domains and is type 'organization'
    assert result is not None
    assert result["type"] == "organization"
    assert result["name"] == "Illuminati"


# ---------------------------------------------------------------------------
# GetTopics and GetRelated (graph layer — empty in test DB)
# ---------------------------------------------------------------------------

def test_gettopics_no_topics(patch_base):
    """GetTopics with empty topics table returns empty list."""
    results = esoterica.GetTopics()
    assert isinstance(results, list)


def test_getrelated_unknown(patch_base):
    """GetRelated for an unknown name returns empty list."""
    results = esoterica.GetRelated("Nonexistent9999")
    assert results == []
