# Changelog

## [Unreleased]

### Changed
- **The Rust core is now the only implementation.** `apocrypha_core` (new,
  under `rust/`) owns HTML normalisation and entity scoring/ranking; the
  duplicate Python copies of `score_entity` and `tags_match` are gone. They
  had already drifted -- the Rust scorer awarded a subsequence bonus the
  Python one did not, and which answer you got depended on whether a wheel had
  been built. A missing extension now raises `RustBackendUnavailable` naming
  the reason instead of silently answering differently.
- `Search()` and `GetFuzzy()` re-rank their SQL candidate pool through
  `rank_entities`, so an exact name match outranks a row that merely mentions
  the word. Rows the scorer gives zero are kept in their original order rather
  than dropped: ranking may reorder, never lose.
- The scraper normalises each board and each feed in one batch call
  (`strip_html_batch`) instead of one call per field, and every per-source
  failure is reported through `ScrapeWarning` instead of a `verbose`-gated
  `print` -- a feed that has been 404ing for months was indistinguishable from
  a feed with no new posts.
- `scripts/scrape.py` catches `json.JSONDecodeError`/`TypeError` around the
  per-row JSON decode rather than a blanket `except Exception`.

### Added
- `assert_rust_backend()`, `backend_report()` and `HAS_RUST`, with a version
  handshake across `pyproject.toml`, the crate's `Cargo.toml`, the package and
  the compiled extension. A stale `_core` left in the tree warns on import and
  is refused by `assert_rust_backend()`.
- `tests/test_backend_surface.py` compares the extension's exported surface
  with the wrapper's re-export list and with `_core.pyi` in both directions,
  so a binding cannot be compiled into the wheel and left unreachable.
- CI runs `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test` and
  `cargo test --features python`.

### Fixed
- **CI tested the published package, not this repository.** The install step
  was `pip install --find-links dist esoterica`, which only *adds* `dist/` to the
  candidate set; pip stayed free to prefer the identically versioned wheel on
  PyPI, and did. Every change in this repository since 1.1.0 went unverified —
  the suite was exercising released code. The built wheel is now installed by
  path.
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

### Changed
- Version bumped to 1.2.0. The working tree had diverged from the published
  1.1.0 while keeping its version number, so `pip install esoterica==1.1.0` and a
  build from this checkout produced different code under one version.

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
