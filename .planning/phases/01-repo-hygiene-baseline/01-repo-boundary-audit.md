# Phase 1 Repository Boundary Audit

## Current State

- `.gitignore` is currently missing from the repository root, which causes git to surface runtime state, caches, and local tooling artifacts as normal workspace noise.
- The repository root mixes tracked project files with local operational files such as `config.yml`, `queue.json`, `retry_queue.json`, `history.json`, `group_history.json`, and `ptbrmerger.log`.
- Generated cache directories currently exist in `.pytest_cache/`, `scripts/__pycache__/`, `src/__pycache__/`, `src/tools/__pycache__/`, `tests/__pycache__/`, and `tests/support/__pycache__/`.
- Local tooling/dev artifacts currently present at the root include `.codex/`, `.runtime-archive/`, `tmp/`, and `get-shit-done-cc-1.28.0.tgz`.

## Tracked vs Local

### Intentionally Tracked

- `src/`
- `tests/`
- `scripts/`
- `README.md`
- `CHANGELOG.md`
- `requirements.txt`
- `config.example.yml`
- `.planning/`
- `.env.example`

### Local-Only Operational Files

- `config.yml`
- `queue.json`
- `retry_queue.json`
- `history.json`
- `group_history.json`
- `ptbrmerger.log`

### Local Tooling / Dev Artifacts

- `.codex/`
- `.codex-repro-readonly/`
- `.codex-repro-write/`
- `.runtime-archive/`
- `tmp/`
- `get-shit-done-cc-1.28.0.tgz`

## Generated Noise

- Python bytecode caches: `__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`
- Pytest cache: `.pytest_cache/`
- Transient API snapshot capture output such as `tests/test_data/api_snapshots/capture_report.json`

## Boundary Decisions

- Track only source code, intentional docs, tracked config templates, and planning artifacts: `src/`, `tests/`, `scripts/`, `README.md`, `CHANGELOG.md`, `requirements.txt`, `config.example.yml`, and `.planning/`.
- Keep operator-specific configuration local: `config.yml` stays untracked and is preserved on disk.
- Keep runtime ledger and log files local: `queue.json`, `retry_queue.json`, `history.json`, `group_history.json`, and `ptbrmerger.log` must not be versioned.
- Ignore generated cache noise by default: `__pycache__/`, `.pytest_cache/`, and Python bytecode files.
- Ignore local tooling/dev artifacts: `.codex/`, `.codex-repro-readonly/`, `.codex-repro-write/`, `.runtime-archive/`, `tmp/`, and `get-shit-done-cc-1.28.0.tgz`.
- Keep `.planning/` tracked intentionally; it is now part of the project workflow rather than disposable local state.

## Safe Cleanup Notes

- Safe to delete generated caches: `.pytest_cache/` and all `__pycache__/` directories.
- Do not delete `config.yml` during cleanup.
- Do not blindly delete `queue.json`, `retry_queue.json`, `history.json`, or `group_history.json`; they are local operator data and should simply fall out of source-control noise once ignore rules are restored.
- Local tooling directories do not need reorganization in this phase; ignoring them is enough to restore repository hygiene.
