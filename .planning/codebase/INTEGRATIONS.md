# Integrations

## Radarr

- Main Radarr integration lives in `src/radarr_client.py`.
- `src/trigger.py` consumes Radarr environment variables for custom-script execution.
- Confirmed Radarr API usage:
  - `GET /api/v3/qualityprofile`
  - `GET /api/v3/tag`
  - `POST /api/v3/tag`
  - `GET /api/v3/movie`
  - `GET /api/v3/release`
  - `PUT /api/v3/movie/editor`
  - `POST /api/v3/movie`
  - `DELETE /api/v3/movie/{id}`
  - `POST /api/v3/command`
- Retry and backoff for transient Radarr failures are implemented with `exponential_backoff()` in `src/radarr_client.py`.

## qBittorrent

- qBittorrent integration lives in `src/qbit_client.py`.
- Authentication uses `/api/v2/auth/login`.
- Confirmed torrent operations:
  - add torrent
  - inspect torrent info
  - list torrents by tag
  - set category
  - add tags
  - resume paused torrents
  - raise/lower queue priority
  - delete torrent and files
- PTBRMerger-specific coordination uses:
  - category `ptbrmerger`
  - tag format `ptbrmerger-tmdbid-<tmdbId>`

## FFmpeg / ffprobe

- Media inspection uses `ffprobe` via subprocess in `src/analyzer.py`.
- Audio extraction and muxing use `ffmpeg` via subprocess in `src/merger.py`.
- Audio fingerprinting also uses `ffmpeg` PCM extraction in `src/audio_fingerprint.py`.

## Discord webhook

- Notification logic lives in `src/notifier.py`.
- Progress refresh tooling lives in `src/tools/refresh_webhook.py`.
- Webhook flow supports:
  - initial POST with `wait=true`
  - PATCH updates to an existing Discord message
  - rich embeds with progress, diagnostics, art, and torrent stats

## Filesystem and local process integration

- Radarr is expected to call `src/trigger.py` as a custom script, documented in `README.md`.
- qBittorrent is expected to call the same trigger on completion using passed placeholders, also documented in `README.md`.
- Local media folders are traversed with `Path.rglob("*.mkv")` in multiple places inside `src/trigger.py` and `src/radarr_client.py`.

## Internal integration boundaries

- `src/trigger.py` is the orchestrator and imports almost every other module.
- Persistence helpers:
  - `src/queue_manager.py`
  - `src/history_manager.py`
  - `src/sync_intelligence.py`
- Operator-facing tools consume the same runtime artifacts rather than separate storage:
  - `src/tools/status.py`
  - `src/tools/reset_queue_entry.py`
  - `src/tools/refresh_webhook.py`
  - `src/tools/tail_log.py`
