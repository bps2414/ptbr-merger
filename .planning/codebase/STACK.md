# Stack

## Runtime and language

- Primary language: Python 3.11+ as documented in `README.md`.
- Source code lives under `src/`.
- Test suite lives under `tests/`.
- Entry script is `src/trigger.py`.
- Utility CLIs live under `src/tools/`.

## Python dependencies

- Runtime dependencies are declared in `requirements.txt`.
- Confirmed packages:
  - `requests`
  - `PyYAML`
  - `loguru`
  - `numpy`
- No `pyproject.toml`, `setup.py`, `poetry.lock`, or `uv.lock` were found at the repo root.

## External binaries

- `ffmpeg` is required for extraction and muxing in `src/merger.py`.
- `ffprobe` is required for stream and duration inspection in `src/analyzer.py`.
- Binary paths are configured through `config.yml` and loaded by `src/config.py`.

## Configuration model

- Typed configuration is implemented with dataclasses in `src/config.py`.
- Config is loaded lazily through `get_config()`.
- The expected config file is the repo-root `config.yml`.
- Sections currently modeled:
  - `radarr`
  - `qbittorrent`
  - `ffmpeg`
  - `sync`
  - `notifications`
  - `logging`
  - `processing`
  - `diagnostics`
  - `scoring`
  - `fingerprint`
  - `ptbr_keywords`

## Operational state files

- Runtime state is stored in repo-root JSON files:
  - `queue.json`
  - `history.json`
  - `group_history.json`
- Logging defaults to `ptbrmerger.log`.
- These files are treated as operational artifacts, not source code.

## Developer tooling

- Tests use `pytest`, visible from imports and test naming under `tests/`.
- Windows helper scripts exist under `scripts/`:
  - `scripts/status.bat`
  - `scripts/watch-log.bat`
  - `scripts/refresh-webhook.bat`
- There is no detected CI pipeline config in the repo root (`.github/workflows`, `azure-pipelines.yml`, etc. were not present in the tracked file list).
