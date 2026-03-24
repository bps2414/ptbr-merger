# Structure

## Top-level layout

- `src/`: production code.
- `tests/`: automated tests.
- `scripts/`: Windows convenience wrappers.
- `conductor/`: planning, product, workflow, and archived track documents.
- `.agents/` and `.codex/`: local agent/system instructions for this workspace.
- `tmp/`: ad hoc local artifact storage.

## Source tree

- `src/trigger.py`
  - main orchestration entrypoint
- `src/config.py`
  - dataclass-based config schema and loader
- `src/analyzer.py`
  - ffprobe analysis and validation helpers
- `src/merger.py`
  - ffmpeg extraction, mux, replace
- `src/radarr_client.py`
  - Radarr API client and release scoring
- `src/qbit_client.py`
  - qBittorrent API client and queue coordination
- `src/notifier.py`
  - logger and Discord embed payloads
- `src/queue_manager.py`
  - queue ledger persistence
- `src/history_manager.py`
  - append-only history persistence
- `src/sync_intelligence.py`
  - release parsing and compatibility history
- `src/audio_fingerprint.py`
  - waveform-based offset detection
- `src/tools/`
  - operator utilities

## Test tree

- Test files are flat under `tests/`, not split into unit/integration subfolders.
- Current files mirror major modules:
  - `tests/test_trigger.py`
  - `tests/test_radarr_client.py`
  - `tests/test_qbit_client.py`
  - `tests/test_merger.py`
  - `tests/test_analyzer.py`
  - `tests/test_audio_fingerprint.py`
  - `tests/test_notifier.py`
  - `tests/test_queue_manager.py`
  - `tests/test_history_manager.py`
  - `tests/test_sync_intelligence.py`
  - `tests/test_tools.py`

## Naming and organization patterns

- Modules use snake_case filenames.
- Tests follow `test_<module>.py`.
- Tools are importable modules under `src/tools/` and callable with `python -m`.
- Operational JSON and log files stay at repo root rather than under a dedicated `var/` or `data/` directory.

## Documentation and planning artifacts

- User-facing documentation: `README.md`.
- Product/process docs: `conductor/product.md`, `conductor/workflow.md`, `conductor/index.md`, `conductor/tracks.md`.
- Historical track artifacts are nested under `conductor/archive/` and `conductor/tracks/`.

## Notable absences

- No package metadata file such as `pyproject.toml`.
- No dedicated `docs/` folder.
- No explicit linter/formatter config files were found in the tracked root files.
- No typed API boundary package or service container layer exists; the structure is intentionally small and script-oriented.
