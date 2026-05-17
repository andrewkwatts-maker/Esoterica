"""Unit tests for esoterica._query — all queries run against an in-memory SQLite DB."""
import pytest
import esoterica
from esoterica._query import (
    Get,
    Search,
    ByTradition,
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
    result = Get("Hermeticism")
    assert result is not None
    assert result["name"] == "Hermeticism"


def test_get_fuzzy(patch_base):
    """Get with lowercase name still finds the entity (case-insensitive)."""
    result = Get("hermeticism")
    assert result is not None
    assert result["name"] == "Hermeticism"


def test_get_partial(patch_base):
    """Get with a substring matches via the LIKE fallback."""
    result = Get("ermeticism")
    assert result is not None
    assert result["name"] == "Hermeticism"


def test_get_none(patch_base):
    """Get with an unknown name returns None."""
    result = Get("Nonexistent9999")
    assert result is None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search(patch_base):
    """Search returns at least one result for a known entity name."""
    results = Search("Hermeticism")
    assert isinstance(results, list)
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "Hermeticism" in names


def test_search_returns_list_on_no_match(patch_base):
    """Search with a non-matching term returns an empty list, never None."""
    results = Search("xyzzy_no_match_99")
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# ByTradition / ByCategory alias
# ---------------------------------------------------------------------------

def test_by_tradition(patch_base):
    """ByTradition('western-esoteric') returns the Hermeticism entry."""
    results = ByTradition("western-esoteric")
    assert len(results) >= 1
    for r in results:
        assert r["mythology"] == "western-esoteric"


def test_by_tradition_case_insensitive(patch_base):
    """ByTradition is case-insensitive."""
    results = ByTradition("WESTERN-ESOTERIC")
    assert len(results) >= 1


def test_by_category_alias(patch_base):
    """ByCategory is an alias for ByTradition; both return the same results."""
    assert ByTradition("ceremonial-magic") == ByCategory("ceremonial-magic")


def test_by_tradition_no_results(patch_base):
    """ByTradition with unknown value returns empty list."""
    results = ByTradition("ancient-sumerian")
    assert results == []


# ---------------------------------------------------------------------------
# ByType
# ---------------------------------------------------------------------------

def test_by_type_tradition(patch_base):
    """ByType('tradition') returns Hermeticism."""
    results = ByType("tradition")
    assert len(results) == 1
    assert results[0]["name"] == "Hermeticism"


def test_by_type_spell(patch_base):
    """ByType('spell') returns Fireball."""
    results = ByType("spell")
    assert len(results) == 1
    assert results[0]["name"] == "Fireball"


def test_by_type_filtered(patch_base):
    """ByType('grimoire', 'ceremonial-magic') returns only The Key of Solomon."""
    results = ByType("grimoire", "ceremonial-magic")
    assert len(results) == 1
    assert results[0]["name"] == "The Key of Solomon"


def test_by_type_no_results(patch_base):
    """ByType with an absent type returns empty list."""
    results = ByType("artifact")
    assert results == []


# ---------------------------------------------------------------------------
# Count
# ---------------------------------------------------------------------------

def test_count_all(patch_base):
    """Count() without filter returns total entity count (5 in test DB)."""
    assert Count() == 5


def test_count_typed(patch_base):
    """Count('tradition') returns 1 (Hermeticism only)."""
    assert Count("tradition") == 1


def test_count_zero_for_missing_type(patch_base):
    """Count with an absent type returns 0."""
    assert Count("artifact") == 0


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
    """GetRandom('spell') returns an entity whose type is 'spell'."""
    result = GetRandom("spell")
    assert result is not None
    assert result["type"] == "spell"


def test_getrandom_mythology(patch_base):
    """GetRandom(mythology='thelema') returns a thelema entity."""
    result = GetRandom(mythology="thelema")
    assert result is not None
    assert result["mythology"] == "thelema"


def test_getrandom_typed_and_mythology(patch_base):
    """GetRandom with both type and mythology filters correctly."""
    result = GetRandom("grimoire", "ceremonial-magic")
    assert result is not None
    assert result["type"] == "grimoire"
    assert result["mythology"] == "ceremonial-magic"


def test_getrandom_no_match_returns_none(patch_base):
    """GetRandom for a type with no entities returns None."""
    result = GetRandom("artifact")
    assert result is None


# ---------------------------------------------------------------------------
# GetFuzzy
# ---------------------------------------------------------------------------

def test_getfuzzy(patch_base):
    """GetFuzzy('Banish') finds Lesser Banishing Ritual via the LIKE fallback."""
    results = GetFuzzy("Banish")
    assert isinstance(results, list)
    assert len(results) >= 1
    names = [r["name"] for r in results]
    assert "Lesser Banishing Ritual" in names


def test_getfuzzy_case_insensitive(patch_base):
    """GetFuzzy is case-insensitive."""
    results = GetFuzzy("banish")
    names = [r["name"] for r in results]
    assert "Lesser Banishing Ritual" in names


def test_getfuzzy_no_match(patch_base):
    """GetFuzzy with no match returns empty list."""
    results = GetFuzzy("xyzzy_nope_9999")
    assert results == []


# ---------------------------------------------------------------------------
# GetMost
# ---------------------------------------------------------------------------

def test_getmost_mythology(patch_base):
    """GetMost('mythology') returns a list including at least one tradition."""
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
    assert "spell" in keys or "ritual" in keys or "tradition" in keys


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
    """GetAll('grimoire') returns the single grimoire entity."""
    results = GetAll("grimoire")
    assert len(results) == 1
    assert results[0]["name"] == "The Key of Solomon"


def test_getall_filtered_mythology(patch_base):
    """GetAll(mythology='thelema') returns only Aleister Crowley."""
    results = GetAll(mythology="thelema")
    assert len(results) == 1
    assert results[0]["name"] == "Aleister Crowley"


def test_getall_filtered_type_and_mythology(patch_base):
    """GetAll('grimoire', 'ceremonial-magic') returns only The Key of Solomon."""
    results = GetAll("grimoire", "ceremonial-magic")
    assert len(results) == 1
    assert results[0]["name"] == "The Key of Solomon"


def test_getall_no_match(patch_base):
    """GetAll with non-existent type returns empty list."""
    results = GetAll("artifact")
    assert results == []


# ---------------------------------------------------------------------------
# Typed helpers defined in esoterica.__init__
# ---------------------------------------------------------------------------

def test_getspell(patch_base):
    """esoterica.GetSpell('Fireball') returns the Fireball entity."""
    result = esoterica.GetSpell("Fireball")
    assert result is not None
    assert result["name"] == "Fireball"
    assert result["type"] == "spell"


def test_getritual(patch_base):
    """esoterica.GetRitual('Lesser Banishing Ritual') returns the LBRP entity."""
    result = esoterica.GetRitual("Lesser Banishing Ritual")
    assert result is not None
    assert result["name"] == "Lesser Banishing Ritual"
    assert result["type"] == "ritual"


def test_gettradition(patch_base):
    """esoterica.GetTradition('Hermeticism') returns the Hermeticism entity."""
    result = esoterica.GetTradition("Hermeticism")
    assert result is not None
    assert result["name"] == "Hermeticism"
    assert result["type"] == "tradition"


def test_getgrimoire(patch_base):
    """esoterica.GetGrimoire('Solomon') finds The Key of Solomon via LIKE."""
    result = esoterica.GetGrimoire("Solomon")
    assert result is not None
    assert result["type"] == "grimoire"


def test_getpractitioner(patch_base):
    """esoterica.GetPractitioner('Crowley') returns the Aleister Crowley entity."""
    result = esoterica.GetPractitioner("Crowley")
    assert result is not None
    assert result["type"] == "practitioner"


def test_typed_helper_wrong_type_returns_none(patch_base):
    """GetSpell with a tradition name returns None (type mismatch)."""
    result = esoterica.GetSpell("Hermeticism")
    assert result is None


def test_typed_helper_domain_fallback(patch_base):
    """_typed falls back to domains_text LIKE; 'conjuration' is in Key of Solomon domains."""
    result = esoterica.GetGrimoire("conjuration")
    assert result is not None
    assert result["type"] == "grimoire"
    assert result["name"] == "The Key of Solomon"


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
