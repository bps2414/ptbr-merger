# Changelog

## v0.3.1 - 2026-03-24

### Fixed
- `SKIPPED_HAS_PTBR` now persists a terminal queue entry and stores `discord_message_id`, so optimized-in-place 4K titles are no longer invisible to later webhook refreshes.
- `refresh_webhook` now updates terminal messages and can recreate a final Discord message from `history.json` when the queue entry is missing.

### Verification
- `pytest -q` -> `71 passed`
- `python -m compileall src tests` -> success
- `python -m src.tools.refresh_webhook --tmdb 1084242` -> `webhooks_updated=1`

## v0.3.0 - 2026-03-24

### Added
- Candidate banks in release selection: `strict`, `soft`, and `exploratory`.
- Config support for `radarr.ptbrmerger_max_candidates`.
- Config thresholds for lighter history scoring on repeated source/group outcomes.

### Changed
- History scoring no longer penalizes generic source pairs like `WEBDL -> WEBDL` as hard compatibility failures.
- Release metadata parsing no longer treats suffixes like `WEB-DL.DUAL.5.1` as release groups.
- Tests now isolate `queue/history/group_history` state and no longer pollute runtime JSON files.
- README updated to describe candidate banks, lighter history scoring, and new config defaults.

### Fixed
- Failed fallback candidates are removed from qBittorrent instead of accumulating after `CUT_MISMATCH`.
- Sonic-style searches no longer get suppressed by stale or synthetic compatibility history.
- Analyzer and trigger tests no longer depend on the operator's local `config.yml`.

### Verification
- `pytest -q` -> `68 passed`
- `python -m compileall src tests` -> success
