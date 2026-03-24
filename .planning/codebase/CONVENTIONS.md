# Conventions

## Code style

- Source files consistently use snake_case for functions and filenames.
- Most modules are function-based rather than class-heavy.
- Dataclasses are used where structured data matters:
  - config objects in `src/config.py`
  - `QbitAddResult` in `src/qbit_client.py`
  - `QueueManager` in `src/queue_manager.py`
- Type hints are used broadly, including `Path | None`, `list[dict]`, and `tuple[...]`.

## Configuration convention

- Modules call `get_config()` at import time and keep a module-level `config`.
- `src/trigger.py` also instantiates long-lived managers at import time.
- This is a stable project convention and tests adapt to it with patching/reassignment rather than constructor injection.

## Error-handling convention

- External integration failures are usually logged and either:
  - retried
  - converted into a status event
  - downgraded to a soft failure so the pipeline can continue safely
- Destructive replacement is protected by explicit validation in `src/merger.py` and `src/analyzer.py`.
- Queue state transitions are explicit: `PENDING`, `PROCESSING`, `FAILED`, `ABANDONED`, `SUCCESS`.

## Observability convention

- Logging uses `loguru` via `src/notifier.py`.
- Console and file logging are both configured centrally there.
- Discord progress/status notifications reuse the same context dict pattern used across the trigger flow.
- History events and compatibility events are JSON serializable dictionaries with UTC timestamps.

## Testing convention

- Tests use `pytest` with plain test functions.
- `unittest.mock.patch` is the dominant mocking strategy.
- Several tests patch module globals directly after import, for example in `tests/test_trigger.py`.
- Temporary files use `tmp_path` rather than custom fixtures for filesystem isolation.

## API/client conventions

- `src/radarr_client.py` wraps all HTTP calls behind `_request()`.
- qBittorrent calls are more direct but still centralized in `src/qbit_client.py`.
- URL construction uses `urljoin`.
- Timeouts are explicitly passed on most requests/subprocesses.

## Content and domain conventions

- PT-BR detection is heuristic-driven, not metadata-schema-driven.
- Release ranking combines:
  - custom format score from Radarr
  - title keyword evidence
  - seed awareness
  - source/group learning from `group_history.json`
- Sync classification uses categorical labels such as `SYNC_OK`, `CUT_MISMATCH`, and `OFFSET_SUSPECTED`.

## Style caveats

- User-facing strings and comments are a PT-BR/English mix.
- A few files show mojibake in terminal output, indicating encoding inconsistencies in some source text or console rendering.
- No formatter-enforced style file was found, so current consistency appears maintained socially and by tests.
