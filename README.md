# PTBRMerger

PTBRMerger is a Python pipeline that sits between Radarr, qBittorrent and FFmpeg to solve a very specific problem:

- detect a newly imported 4K movie in Radarr
- check whether the 4K file already has native PT-BR audio
- if not, search Radarr releases for a compatible 1080p PT-BR / dual-audio source
- inject that source directly into qBittorrent
- wait for qBittorrent to finish
- extract the PT-BR track and mux it into the original 4K file
- validate the final MKV before replacing the original

Phase 2 hardening is already implemented in this repository. The current pipeline includes:

- direct qBittorrent bypass mode with duplicate detection by infohash
- PT-BR ranking with explicit weighting for `dublado`, `dual` and BR signals
- multi-bank candidate search with `strict`, `soft` and `exploratory` fallback banks
- seed-awareness before qBittorrent injection, skipping dead torrents with `0` seeders
- qBittorrent queue bias that raises active `ptbrmerger` downloads above `radarr`
- runtime/sync diagnostics with structured classification
- operational ledger in `queue.json`
- structured execution history in `history.json`
- final-file validation before destructive replacement
- Radarr success feedback via `ptbr-merged`
- Discord webhook progress updates with editable embeds
- compatibility learning in `group_history.json` with lighter penalties for generic sources
- conservative auto-offset for clearly eligible `OFFSET_SUSPECTED` candidates
- NumPy-based audio fingerprinting for higher-confidence offset decisions

## Stack

- Python 3.11+
- FFmpeg / FFprobe
- Radarr v3/v4
- qBittorrent API v2
- `requests`, `PyYAML`, `loguru`

## Repository Layout

```text
src/
  analyzer.py         ffprobe analysis, language detection, sync diagnostics
  config.py           typed config loader
  history_manager.py  append-only history persistence
  merger.py           extract, mux and safe replace
  notifier.py         logs + Discord embeds
  qbit_client.py      qBittorrent API integration
  queue_manager.py    lightweight processing ledger
  radarr_client.py    Radarr API + retry/backoff + success tag
  trigger.py          orchestration entrypoint for Radarr/qBittorrent events

tests/
  unit and integration-style coverage for analyzer, notifier, trigger, queue, history, qbit and Radarr client
```

## Current Flow

### Flow A: 4K already has PT-BR audio

1. Radarr triggers `src/trigger.py` on import or upgrade.
2. `src/analyzer.py` inspects the 4K file with `ffprobe`.
3. If PT-BR audio already exists, the project runs in-place optimization only.
4. The final MKV keeps the useful streams and avoids unnecessary leftovers.

### Flow B: 4K has no PT-BR audio

1. Radarr triggers `src/trigger.py`.
2. `src/analyzer.py` confirms the 4K file does not contain PT-BR audio.
3. `src/radarr_client.py` searches releases and ranks candidates in banks:
   - `strict`: explicit PT-BR evidence
   - `soft`: relaxed PT-BR evidence
   - `exploratory`: dual/multi fallback candidates kept as last resort
4. Releases with `0` seeders are discarded before qBittorrent injection whenever Radarr provides availability metadata.
5. `src/qbit_client.py` injects the chosen torrent into qBittorrent with:
   - category: `ptbrmerger`
   - tag: `ptbrmerger-tmdbid-<tmdbId>`
   - queue priority favoring active `ptbrmerger` downloads over `radarr`
6. qBittorrent calls the same trigger again on torrent completion.
7. `src/trigger.py` resolves the finished 1080p source, loads the original 4K and runs:
   - sync diagnosis
   - stream detection
   - PT-BR extraction
   - mux
   - final validation
8. Only after validation succeeds, the original 4K file is replaced.
9. Radarr is rescanned and tagged with `ptbr-merged`.
10. The qBittorrent torrent is removed only after real success.

## Phase 2 Safety Guarantees

The current codebase is no longer a simple “extract and replace” script. It has operational safeguards:

- `queue.json`
  Prevents duplicate processing and tracks `PENDING`, `PROCESSING`, `FAILED`, `ABANDONED`, `SUCCESS`.

- `history.json`
  Stores structured events such as candidate selection, fallback, failure cause, runtimes and success.

- `group_history.json`
  Stores compatibility outcomes by release group and source pairing so future searches can promote known-good combos without over-penalizing generic `WEBDL -> WEBDL` cases.

- Audio fingerprint sync
  For `OFFSET_SUSPECTED` candidates, the pipeline can sample short PCM windows from the 4K and 1080p files, correlate them and decide between:
  - `FINGERPRINT_SYNC_OK`
  - `FINGERPRINT_OFFSET_OK`
  - `FINGERPRINT_DRIFT_SUSPECTED`
  - `FINGERPRINT_CUT_MISMATCH`
  - `FINGERPRINT_LOW_CONFIDENCE`

- Seed-aware search
  Releases with `seeders <= 0` are skipped before injection when Radarr exposes availability data. If all acceptable candidates are dead, the history records `NO_AVAILABLE_SEEDS`.

- Sync diagnosis
  The pipeline classifies candidates as:
  - `SYNC_OK`
  - `CUT_MISMATCH`
  - `OFFSET_SUSPECTED`
  - `RUNTIME_INCOMPATIBLE`
  - `UNKNOWN_SYNC_FAILURE`

- Conservative auto-offset
  Only `OFFSET_SUSPECTED` candidates that pass confidence and maximum-offset gates are retried with `-itsoffset`. Structural mismatches still go straight to fallback.

- Exploratory fallback bank
  Releases that do not meet the strict PT-BR gate but still look plausibly useful, such as generic `dual/multi` titles, can be preserved as last-resort fallback candidates instead of being discarded immediately.

- Final-file validation
  The final MKV is checked for:
  - presence of PT-BR audio
  - duration compatibility with the original 4K
  - coherent output before replacement

- Retry/backoff
  Radarr API calls retry only on transient failures like timeout, connection issues, `429` and `5xx`.

- Discord status editing
  The webhook creates one message and updates it as the process advances.

## Installation

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Project dependencies:

```text
requests>=2.31.0
PyYAML>=6.0
loguru>=0.7.0
```

## Configuration

Create `config.yml` at the repository root.

Example:

```yaml
radarr:
  url: http://localhost:7878
  api_key: YOUR_RADARR_API_KEY
  ptbrmerger_profile_name: PTBRMerger
  ptbrmerger_root_folder: D:\data\temp\ptbrmerger
  ptbrmerger_tag_name: ptbrmerger
  ptbrmerger_min_score: 10000
  ptbrmerger_max_candidates: 10
  timeout: 10
  success_tag_label: ptbr-merged

qbittorrent:
  url: http://localhost:8080
  username: admin
  password: adminadmin

ffmpeg:
  ffmpeg_path: ffmpeg
  ffprobe_path: ffprobe

sync:
  max_duration_diff_seconds: 30

notifications:
  discord_webhook_url: ""
  username: PTBRMerger Bot

logging:
  level: INFO
  file: ptbrmerger.log
  history_file: history.json
  history_max_entries: 500

processing:
  queue_file: queue.json
  max_attempts: 3
  preserve_failed_artifacts: true

diagnostics:
  enable_runtime_heuristics: true
  enable_offset_diagnostics: true
  offset_suspected_threshold_seconds: 180
  enable_auto_offset: false
  auto_offset_max_seconds: 90
  auto_offset_min_confidence: 0.85

scoring:
  history_bonus_success: 8
  history_penalty_cut_mismatch: 18
  history_penalty_runtime_incompatible: 14
  history_min_group_samples: 2
  history_min_source_samples: 2

fingerprint:
  enabled: false
  sample_rate: 2000
  window_seconds: 12
  max_offset_seconds: 90
  min_confidence: 0.7
  consistency_tolerance_seconds: 0.75
  positions:
    - head
    - mid
    - tail
  allow_borderline_cut_retry: false

ptbr_keywords:
  high_priority:
    - "pt-br"
    - "ptbr"
    - "portuguese"
  medium_priority:
    - "dual"
    - "multi"
  indexer_names_br:
    - "Catálogo Betor"
  blacklist:
    - "CAM"
    - "TELECINE"
```

## Radarr Setup

Register a Custom Script in Radarr:

1. Go to `Settings -> Connect -> + -> Custom Script`
2. Configure:
   - `Name`: `PTBRMerger`
   - `On Import`: enabled
   - `On Upgrade`: enabled
   - `Path`: full Python executable path or `python`
   - `Arguments`: absolute path to `src/trigger.py`
3. Use the `Test` button to confirm Radarr can run the trigger.

Example:

```bash
python D:\ptbr-merger\src\trigger.py
```

## qBittorrent Setup

The bypass flow depends on qBittorrent finishing the PT-BR candidate and notifying the trigger.

You should configure qBittorrent to run an external program on torrent completion, pointing to the same trigger and passing the qBittorrent placeholders used by the project.

The important expectations are:

- torrents injected by PTBRMerger must use category `ptbrmerger`
- the torrent must keep the tag `ptbrmerger-tmdbid-<tmdbId>`
- qBittorrent must call `src/trigger.py` when the download completes

## Manual Run / Dry Run

You can simulate the Radarr entrypoint manually:

```bash
python src/trigger.py --file-path "D:\Movies\Movie4K.mkv" --dry-run
```

Or set:

```powershell
$env:PTBRMERGER_DRY_RUN="true"
```

In dry-run mode the project logs the intended FFmpeg and API actions without mutating files or deleting torrents.

## Operational Commands

Tail the current log without opening an editor:

```bash
python -m src.tools.tail_log --lines 80 --follow
```

Or on Windows:

```bat
scripts\watch-log.bat
```

Show queue, recent history and `ptbrmerger` torrents:

```bash
python -m src.tools.status
```

Or on Windows:

```bat
scripts\status.bat
```

Reset one movie from the ledger by TMDB ID:

```bash
python -m src.tools.reset_queue_entry --tmdb 680493
```

Force an immediate Discord webhook refresh using the current qBittorrent state:

```bash
python -m src.tools.refresh_webhook --tmdb 945961
```

Or on Windows:

```bat
scripts\refresh-webhook.bat --tmdb 945961
```

## Runtime Files

The project creates lightweight operational files in the repository root by default:

- `queue.json`
- `history.json`
- `group_history.json`

These are gitignored in this repository because they are runtime state, not source code.

## Testing

Run the current automated suite:

```bash
pytest -q
```

The repository currently includes coverage for:

- stream detection and sync diagnosis
- qBittorrent injection and duplicate handling
- Radarr retry/tag behavior
- Discord embed generation and editable progress messages
- queue/history persistence
- trigger orchestration and final validation paths

## Notes

- The pipeline validates the final MKV before replacing the original file.
- qBittorrent cleanup happens only after a successful merge path.
- The final filename may remain cosmetically unchanged even when internal streams are updated correctly.
- `ptbr-merged` is the success feedback tag currently written back to Radarr.
