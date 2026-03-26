# Milestones

## v0.4.0 Sync Recovery (Shipped: 2026-03-26)

**Phases completed:** 5 phases, 14 plans, 22 tasks

**Key accomplishments:**

- Classified large runtime mismatches into recoverable versus terminal categories instead of discarding every large-diff candidate immediately.
- Added conservative automatic sync recovery with explicit post-validation before any destructive replacement.
- Added assisted/manual recovery controls with persisted offset, trim, and replay metadata for operator retries.
- Made recovery outcomes visible across notifier, queue/history, status tooling, and webhook refresh flows.
- Closed the milestone with fixture-backed coverage for recoverable and unrecoverable sync-recovery scenarios.
- Normalized verification artifacts across phases so the milestone audit could pass cleanly.

---

## v0.3.5 Hygiene Baseline

**Shipped:** 2026-03-25
**Phases:** 1
**Plans:** 3
**Status:** Completed with intentionally reduced scope

### Delivered

- Audited the repository boundary and documented tracked versus local-only artifacts
- Restored `.gitignore` to exclude runtime state, caches, logs, and local tooling artifacts
- Removed tracked Python bytecode from the repository index and cleaned cache directories
- Added contributor-facing repository hygiene guidance to `README.md`
- Validated the hygiene outcome with Phase 1 UAT (`3/3` pass)

### Known Deferred Work

- Trigger decomposition (originally planned as Phase 2)
- Ranking domain extraction (originally planned as Phase 3)
- Validation workflow consolidation (originally planned as Phase 4)
