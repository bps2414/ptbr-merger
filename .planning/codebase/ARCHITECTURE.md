# Architecture

## System shape

- The codebase is a single-process Python service script, not a web server.
- The dominant architecture is orchestration-centric: `src/trigger.py` coordinates analysis, search, download handoff, merge, validation, and cleanup.
- Most modules are thin service modules with module-level config and functions instead of classes.

## Main flow

1. `src/trigger.py` receives either:
   - a Radarr import/upgrade event
   - a qBittorrent completion event
   - a manual dry-run invocation
2. `src/analyzer.py` inspects the original 4K file.
3. `src/radarr_client.py` searches and ranks PT-BR candidates when needed.
4. `src/qbit_client.py` injects or reuses the chosen torrent in qBittorrent.
5. qBittorrent completion routes back into `src/trigger.py`.
6. `src/analyzer.py` and optionally `src/audio_fingerprint.py` evaluate compatibility.
7. `src/merger.py` extracts audio, muxes output, validates it, and replaces the original.
8. `src/radarr_client.py` rescans the movie and applies the success tag.
9. `src/notifier.py` emits local logs and Discord updates across the flow.

## State and persistence model

- Stateful orchestration is file-backed rather than database-backed.
- `src/queue_manager.py` owns the live per-TMDB processing ledger.
- `src/history_manager.py` stores append-only event history.
- `src/sync_intelligence.py` stores cross-run compatibility history in `group_history.json`.
- This keeps the runtime simple, but it also means cross-process coordination depends on JSON file correctness.

## Domain modules

- `src/config.py`: typed config loader.
- `src/analyzer.py`: ffprobe inspection, PT-BR detection, duration checks, sync diagnosis, final validation.
- `src/radarr_client.py`: release search, ranking, tagging, rescan, retry logic.
- `src/qbit_client.py`: torrent lifecycle and queue-priority control.
- `src/merger.py`: ffmpeg extraction, muxing, validation, destructive replacement.
- `src/audio_fingerprint.py`: NumPy-based offset measurement and classification.
- `src/sync_intelligence.py`: release metadata parsing plus historical scoring.
- `src/notifier.py`: console/file logging and Discord embed generation.

## Architectural style details

- Heavy use of module globals:
  - `config = get_config()`
  - singleton-ish managers in `src/trigger.py`
  - module-level caches in `src/radarr_client.py`
- Dependency injection is mostly absent; tests rely on `unittest.mock.patch`.
- Error handling is pragmatic and status-driven: failures are often converted into queue/history updates plus fallback attempts.

## Entry points

- Main runtime entry: `src/trigger.py`.
- Secondary operator entry points:
  - `python -m src.tools.status`
  - `python -m src.tools.tail_log`
  - `python -m src.tools.reset_queue_entry`
  - `python -m src.tools.refresh_webhook`

## Data flow boundaries

- External APIs are called directly from service modules with `requests`.
- Media operations are isolated behind subprocess calls.
- Orchestration and business rules are concentrated in `src/trigger.py` and `src/radarr_client.py`.
