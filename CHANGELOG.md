# Changelog

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
