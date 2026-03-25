# Changelog

## v0.3.5 - 2026-03-25

### Added
- Phase 3E operational tooling with `src/tools/preflight.py` and `src/tools/runtime_hygiene.py`.
- Windows launchers `scripts/preflight.bat` and `scripts/runtime-hygiene.bat`.
- Test coverage for preflight, runtime hygiene, Bazarr notification context and richer rejection summaries.

### Changed
- `NOT_FOUND` and `NO_AVAILABLE_SEEDS` messages now surface Bazarr fallback status when present.
- Radarr candidate search now logs a compact rejection summary, including low-score and missing-URL cases.

### Verification
- `pytest -q tests/test_tools.py tests/test_notifier.py tests/test_radarr_client.py` -> `30 passed`
- `python -m src.tools.preflight --json` -> `BLOCKER` in this environment because qBittorrent is offline and Bazarr lacks config
- `python -m src.tools.runtime_hygiene --json` -> dry-run plan generated
- `pytest -q` -> `101 passed`
- `python -m compileall src tests` -> success

## v0.3.4 - 2026-03-25

### Added
- Phase 3D API snapshot compatibility layer with sanitized fixtures for Radarr, qBittorrent and Bazarr payloads.
- `tests/test_api_snapshots.py` covering real-field compatibility, infohash preservation and Bazarr payload wrappers.
- `tests/support/api_snapshots.py` with reusable payload sanitizers and snapshot writer helpers.
- `scripts/capture_api_snapshots.py` to capture sanitized snapshots from local live services when available.

### Changed
- qBittorrent injection now accepts a known Radarr `infoHash` and prefers it over resolving a magnet redirect chain.
- Trigger orchestration now forwards release `infohash` into qBittorrent injection for both primary selection and fallback.
- Bazarr lookup now accepts both raw-list and wrapped-object payloads.

### Verification
- `pytest -q tests/test_api_snapshots.py tests/test_trigger.py tests/test_radarr_client.py tests/test_qbit_client.py` -> `38 passed`
- `pytest -q` -> `94 passed`
- `python -m compileall src tests` -> success

## v0.3.3 - 2026-03-25

### Added
- Phase 3C local real-media fixture corpus with deterministic MKV samples generated on demand.
- `tests/test_media_integration.py` covering optimize-only, real merge, fingerprint offset detection, structural mismatch rejection, chapter/subtitle preservation and validation failure without PT-BR.
- `tests/test_data/media_fixtures/manifest.json` as the versioned fixture manifest.
- `scripts/generate_media_fixtures.py` to regenerate the corpus without downloading real movies.

### Changed
- Test coverage now includes a real local integration layer using `ffmpeg/ffprobe`, not only mocks.

### Verification
- `pytest -q tests/test_media_integration.py` -> `10 passed`
- `pytest -q` -> `88 passed`
- `python -m compileall src tests` -> success

## v0.3.2 - 2026-03-25

### Added
- `retry_queue.json` and `RetryQueueManager` for recoverable failures.
- `python src/trigger.py --retry-pending` to replay due retries.
- Partial candidate pre-check based on evidence level, seeds and compatibility history.
- Optional Bazarr subtitle lookup on `NOT_FOUND` / `NO_AVAILABLE_SEEDS`.

### Changed
- `status` output now includes the retry queue.
- Discord embeds now show retry scheduling, pre-check result and Bazarr fallback status.
- Candidate selection logs now record `precheck_result` and structured rejection buckets.

### Verification
- `pytest D:\\ptbr-merger\\tests\\test_retry_queue_manager.py D:\\ptbr-merger\\tests\\test_radarr_client.py D:\\ptbr-merger\\tests\\test_trigger.py D:\\ptbr-merger\\tests\\test_tools.py D:\\ptbr-merger\\tests\\test_notifier.py -q` -> `42 passed`
- `python -m compileall src tests` -> success

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
