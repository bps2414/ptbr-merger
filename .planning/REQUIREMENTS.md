# Requirements: PTBRMerger (No Active Milestone)

**Defined:** 2026-03-25
**Core Value:** When a 4K movie lacks PT-BR audio, the pipeline must recover a compatible PT-BR source and merge it safely without corrupting or wrongly replacing the original file.

## Current Status

There is no active milestone in progress right now. The most recent shipped milestone was archived as `v0.3.5 Hygiene Baseline`.

Archived requirements: `.planning/milestones/v0.3.5-REQUIREMENTS.md`

## Deferred Candidate Requirements

These are not committed to an active roadmap yet, but they remain likely candidates for the next milestone:

- **ORCH-01**: Split orchestration responsibilities currently concentrated in `src/trigger.py`
- **ORCH-02**: Preserve trigger behavior while refactoring orchestration boundaries
- **ORCH-03**: Keep trigger-focused automated coverage intact during refactor
- **RANK-01**: Extract Radarr candidate ranking and fallback rules into dedicated modules
- **RANK-02**: Preserve strict/soft/exploratory ranking behavior with focused tests
- **RANK-03**: Reduce ranking-change blast radius on API-client behavior
- **QUAL-01**: Define a single validation entrypoint for test and compile checks
- **QUAL-02**: Make validation repeatable in the local workflow
- **QUAL-03**: Keep contributor docs aligned with the current validation path

## Traceability

No active milestone traceability table yet.

---
*Requirements defined: 2026-03-25*
*Last updated: 2026-03-25 after archiving v0.3.5 Hygiene Baseline*
