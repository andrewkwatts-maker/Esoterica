# Changelog

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
