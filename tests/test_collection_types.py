"""`_COLLECTION_TYPES` must agree with the types the data actually declares.

The map is only the fallback for a Firestore document that carries no `type`
of its own. When it disagrees with the documents, delta-synced rows land under
a type nothing queries and sit invisibly beside their baked siblings — which
is exactly what `herbs -> ingredient` did to all 127 herbs, and
`magic -> tradition` to all 106 magic systems.
"""
from pathlib import Path

import esoterica
from esoterica._query import (
    MAGIC_COLLECTIONS,
    ByType,
    Count,
    GetAll,
    GetRandom,
    _COLLECTION_TYPES,
    _expand_types,
)

# The types present in the shipped data-v1.1.0 snapshot, with their row counts.
BAKED_TYPES = {"ritual": 281, "herb": 127, "magic": 106, "collection": 2,
               "druidic-magic": 1}


# ── the mapping itself ────────────────────────────────────────────────────────

def test_every_collection_is_mapped():
    assert set(MAGIC_COLLECTIONS) == set(_COLLECTION_TYPES)


def test_legacy_collections_map_to_the_type_their_documents_declare():
    assert _COLLECTION_TYPES["herbs"] == "herb"
    assert _COLLECTION_TYPES["magic"] == "magic"


def test_bake_script_uses_the_same_mapping():
    """A re-bake must produce the types the query layer expects."""
    # Read rather than import: scripts/bake.py requires `requests` at import.
    src = (Path(__file__).resolve().parents[1] / "scripts" / "bake.py").read_text(
        encoding="utf-8"
    )
    for collection, entity_type in _COLLECTION_TYPES.items():
        assert f'"{collection}": "{entity_type}"' in src, collection


def test_mapped_types_that_the_snapshot_populates_are_reachable():
    """Guards the regression: no mapping may point at a type the baked rows
    do not use unless the getters explicitly span both spellings."""
    for collection in ("herbs", "magic", "rituals"):
        assert _COLLECTION_TYPES[collection] in BAKED_TYPES, collection


# ── the getters span both spellings ───────────────────────────────────────────

def test_get_ingredient_finds_a_herb(patch_legacy_base):
    result = esoterica.GetIngredient("Mandrake")
    assert result is not None
    assert result["type"] == "herb"


def test_get_herb_finds_a_herb(patch_legacy_base):
    assert esoterica.GetHerb("Mandrake")["name"] == "Mandrake"


def test_get_tradition_finds_a_magic_system(patch_legacy_base):
    result = esoterica.GetTradition("Hoodoo")
    assert result is not None
    assert result["type"] == "magic"


def test_get_tradition_still_finds_a_real_tradition(patch_legacy_base):
    assert esoterica.GetTradition("Hermeticism")["type"] == "tradition"


def test_by_type_spans_aliases(patch_legacy_base):
    assert {r["name"] for r in ByType("tradition")} == {"Hermeticism", "Hoodoo Rootwork"}
    assert {r["name"] for r in ByType("ingredient")} == {"Mandrake"}
    assert _expand_types("ingredient") == ("ingredient", "herb")
    assert _expand_types("spell") == ("spell",)


def test_count_and_getall_span_aliases(patch_legacy_base):
    assert Count("tradition") == 2
    assert len(GetAll("tradition")) == 2
    assert Count("ingredient") == 1


def test_getrandom_spans_aliases(patch_legacy_base):
    assert GetRandom("ingredient")["name"] == "Mandrake"
    assert GetRandom("ingredient", "folk-magic")["name"] == "Mandrake"


def test_unaliased_types_are_not_widened(patch_legacy_base):
    assert Count("spell") == 1
    assert esoterica.GetSpell("Mandrake") is None
