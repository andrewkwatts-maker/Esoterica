# Changelog

## [Unreleased]

### Fixed
- **`_COLLECTION_TYPES` disagreed with the data it describes.** `herbs` mapped
  to `ingredient` and `magic` to `tradition`, but all 127 baked herb rows and
  all 106 baked magic rows declare `herb` and `magic` — the types come from
  the source documents, and the map is only the fallback for a document with
  no type of its own. A delta-synced herb therefore landed under `ingredient`,
  a type with zero baked rows and no queries, invisible next to its 127
  siblings. Both mappings now follow the documents, in `scripts/bake.py` as
  well, so a re-bake and a sync agree.
- `GetIngredient()`/`GetTradition()`, and `ByType`/`Count`/`GetAll`/`GetRandom`
  for those two types, span both spellings, so callers written against the old
  names keep working against the snapshot that is already installed.

### Added
- `GetHerb()`, naming the type the corpus actually uses.
- The expected SHA-256 of the release asset is declared next to its URL and
  verified during download; a mismatch fails hard and caches nothing.

### Notes
- Four of the nine declared collections — `spells`, `traditions`, `grimoires`,
  `practitioners` — contributed zero rows to the data-v1.1.0 bake, as did
  `ingredients` and `artifacts`. The declarations are deliberately kept: they
  are the collections the site will populate, and dropping them would stop
  `Refresh()` from ever seeing their first document.

## [1.1.0] — 2026-08-30

### Added
- **First release that ships data**: 519 entities (281 rituals, 138 herbs,
  108 magic traditions) baked from the eyesofazrael Firestore.
- Lazy data download: `esoterica.db.gz` is a GitHub Release asset
  (data-v1.1.0) fetched on first query via `eyecore>=1.1.0` — not in git,
  not in the wheel.
- `esoterica.Refresh()` — merges Firestore changes since the bake epoch.
- `scripts/bake.py` stamps `meta.generated_at`.

### Fixed
- bake.py conspiracy-era leftovers: empty default project id, "Conspiracy
  category" topic descriptions, wrong CLI description.
- `scripts/scrape.py` imported from the abandoned `apocrypha` package name.

## [1.0.1] — 2026-05-17

Magic-systems identity restored (reverted the conspiracy detour). No data shipped.
