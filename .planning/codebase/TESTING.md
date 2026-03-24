# Testing

## Framework and layout

- The project uses `pytest`.
- Tests are stored directly under `tests/`.
- There is no separate `integration/`, `fixtures/`, or `conftest.py` structure in the tracked files.

## Coverage by area

- `tests/test_trigger.py`
  - end-to-end orchestration scenarios around `run_analyzer()` and `run_merger()`
  - fallback behavior
  - duplicate torrent reuse
  - auto-offset and fingerprint-driven branches
- `tests/test_radarr_client.py`
  - retry behavior
  - tagging
  - release filtering and ranking
- `tests/test_qbit_client.py`
  - add/reuse logic
  - duplicate handling
  - queue prioritization
- `tests/test_merger.py`
  - ffmpeg command construction
  - transient retry behavior
  - validation gate before replacement
- `tests/test_analyzer.py`
  - stream preservation
  - sync diagnosis
  - final-file validation
- `tests/test_audio_fingerprint.py`
  - offset measurement/classification logic
- `tests/test_notifier.py`
  - Discord payload behavior
- `tests/test_queue_manager.py`, `tests/test_history_manager.py`, `tests/test_sync_intelligence.py`, `tests/test_tools.py`
  - JSON persistence and operator utilities

## Test techniques

- Extensive use of `patch()` to isolate:
  - subprocess calls
  - HTTP calls
  - qBittorrent/Radarr side effects
  - module singletons and config flags
- Filesystem state is isolated with `tmp_path`.
- Tests assert command arguments and resulting state transitions, not only return values.

## What is covered well

- Core orchestration branching in `src/trigger.py`.
- Ranking heuristics and retry semantics in `src/radarr_client.py`.
- qBittorrent duplicate/reuse flows in `src/qbit_client.py`.
- Safety gates before destructive replacement in `src/merger.py`.

## Likely gaps

- No real integration tests against live Radarr/qBittorrent/FFmpeg instances.
- No explicit coverage report configuration or threshold was found.
- No automated tests were seen for the actual CLI argument parsing of each tool module.
- No property-based or fuzz-style tests were found for release-title parsing in `src/sync_intelligence.py`.

## How tests are expected to run

- `README.md` documents `pytest -q`.
- The suite appears designed to run locally without external services because external edges are mocked.
- Test data is minimal; only `tests/test_data/movie_folder/dummy_1080p.mkv` was observed as a tracked media fixture.
