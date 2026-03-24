# Concerns

## Architectural risks

- `src/trigger.py` is a very large orchestration module with many responsibilities: event parsing, state management, fallback policy, progress updates, merge execution, and cleanup.
- Module-level singletons (`config`, queue/history managers, caches) make import order and test isolation more fragile than constructor-based wiring.
- File-backed state in `queue.json`, `history.json`, and `group_history.json` has no locking, so concurrent triggers could race on read-modify-write paths.

## Operational risks

- The project stores runtime artifacts in the repository root:
  - `queue.json`
  - `history.json`
  - `group_history.json`
  - `ptbrmerger.log`
- That is simple, but it couples runtime health to the working directory and can pollute the repo during long-lived operation.
- The sample `config.yml` present in the workspace is a real file path, so accidental local secrets exposure is a practical risk even though generated docs avoid copying values.

## Integration risks

- `src/qbit_client.py` and `src/radarr_client.py` depend directly on external API response shapes with limited schema validation.
- `src/qbit_client.py` attempts several recovery heuristics around duplicate detection and redirect-based infohash extraction; those branches are valuable but can be brittle against client/indexer changes.
- Radarr and qBittorrent behavior is covered mostly by mocks, not live integration tests.

## Media-processing risks

- All critical media work depends on subprocess calls to `ffmpeg` and `ffprobe`.
- There is retry logic for transient mux failures in `src/merger.py`, but no central subprocess wrapper or structured stderr parsing.
- Destructive replacement is guarded, yet failures after partial external side effects still require careful operator recovery.

## Code-quality concerns

- Some files exhibit mojibake in rendered PT-BR strings, suggesting encoding inconsistency or terminal mismatch.
- There is no detected formatter/linter configuration, so consistency depends on discipline and tests.
- The repo currently lacks a formal CI definition, so validation appears manual or tool-driven outside the repo.

## Testing concerns

- Coverage is strong around mocked behavior, but confidence in real FFmpeg/Radarr/qBittorrent interoperability remains lower.
- The absence of concurrency tests is notable given the JSON-backed queue/history design.
- `tests/test_trigger.py` is large and behavior-dense; future changes in orchestration may become harder to reason about without further decomposition.

## Maintainability hotspots

- `src/trigger.py`
- `src/radarr_client.py`
- `src/qbit_client.py`
- `src/notifier.py`

These files hold most policy and integration complexity and are the most likely places for regressions when the pipeline evolves.
