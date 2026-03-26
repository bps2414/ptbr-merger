# Roadmap: PTBRMerger

## Overview

The active roadmap now targets operator-guided local usage. The product already has strong recovery behavior, but too much of that power still depends on raw terminal knowledge. This milestone makes the system safer and more approachable for non-technical operation without jumping straight to a full dashboard.

## Milestones

- ✓ **v0.3.5 Hygiene Baseline** - Phase 1 only (shipped 2026-03-25)
- ✓ **v0.4.0 Sync Recovery** - Phases 2-5 (shipped 2026-03-26)
- 🚧 **v0.4.5 Guided Operations** - Phases 6-9 (planned)

## Archived Milestones

<details>
<summary>✓ v0.4.0 Sync Recovery - SHIPPED 2026-03-26</summary>

- [x] Phase 2: Recoverability Diagnostics (3/3 plans) - completed 2026-03-25
- [x] Phase 3: Automatic Sync Recovery (3/3 plans) - completed 2026-03-26
- [x] Phase 4: Assisted Recovery And Outcomes (3/3 plans) - completed 2026-03-26
- [x] Phase 5: Verification Closure And Traceability (2/2 plans) - completed 2026-03-26

</details>

Archived details: `.planning/milestones/v0.4.0-ROADMAP.md`

<details>
<summary>✓ v0.3.5 Hygiene Baseline - SHIPPED 2026-03-25</summary>

- [x] Phase 1: Repo Hygiene Baseline (3/3 plans) - completed 2026-03-25

</details>

Archived details: `.planning/milestones/v0.3.5-ROADMAP.md`

## Active Milestone: v0.4.5 Guided Operations

**4 phases** | **12 requirements mapped** | All covered ✓

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 6 | Operator Command Center | Create one guided entrypoint that exposes the main local operations without requiring the user to memorize commands | OPS-01, OPS-02, OPS-03 | 4 |
| 7 | Doctor And Safe Maintenance | Add a plain-language doctor flow and safer maintenance confirmations for risky local actions | DOC-01, DOC-02, DOC-03, SAFE-OPS-01 | 4 |
| 8 | Guided Manual Recovery | Turn manual recovery into a prompt-driven guided flow with validation and execution preview | REC-UX-01, REC-UX-02, REC-UX-03, SAFE-OPS-02 | 4 |
| 9 | Human-Facing Operator Docs | Align docs and operator scripts with the guided flow in Portuguese for real local usage | GUIDE-01 | 3 |

### Phase Details

**Phase 6: Operator Command Center**
Goal: give the operator a single guided local entrypoint for the most common actions instead of forcing raw CLI recall.
Requirements: OPS-01, OPS-02, OPS-03
Success criteria:
1. A user can launch one command or script and see the main operational actions immediately.
2. The guided flow covers at least status, doctor, manual recovery, webhook refresh, and safe maintenance entrypoints.
3. The flow explains what each action does before execution.
4. The flow ends each action with a clear next-step prompt instead of dumping the user back into ambiguity.

**Phase 7: Doctor And Safe Maintenance**
Goal: help the operator understand local blockers early and prevent accidental destructive maintenance actions.
Requirements: DOC-01, DOC-02, DOC-03, SAFE-OPS-01
Success criteria:
1. A single doctor/preflight command checks the most important local dependencies and config expectations.
2. Problems are reported in plain language with clear fix suggestions.
3. Blocking issues are separated from warnings.
4. State-mutating maintenance actions require explicit confirmation inside the guided flow.

**Phase 8: Guided Manual Recovery**
Goal: make manual recovery usable by someone who understands the intent but not the raw trigger syntax.
Requirements: REC-UX-01, REC-UX-02, REC-UX-03, SAFE-OPS-02
Success criteria:
1. The operator can start manual recovery through prompts instead of memorizing trigger flags.
2. Invalid parameter combinations are rejected before execution begins.
3. The user can review the chosen recovery recipe before it runs.
4. The flow clearly marks whether it is read-only, previewing, or mutating.

**Phase 9: Human-Facing Operator Docs**
Goal: make the guided operations flow discoverable and repeatable through operator-facing scripts and docs.
Requirements: GUIDE-01
Success criteria:
1. README and operator docs describe the guided workflow in Portuguese.
2. Entry scripts/shortcuts match the documented commands.
3. A non-technical operator can follow the documented path for common operations without needing raw CLI knowledge.

## Deferred Candidate Work

- Trigger decomposition - originally planned as Phase 2, deferred before execution
- Ranking domain extraction - originally planned as Phase 3, deferred before execution
- Validation workflow - originally planned as Phase 4, deferred before execution

## Progress

| Milestone | Scope | Status | Completed |
|-----------|-------|--------|-----------|
| v0.3.5 Hygiene Baseline | Phase 1 only | Complete | 2026-03-25 |
| v0.4.0 Sync Recovery | Phases 2-5 | Complete | 2026-03-26 |
| v0.4.5 Guided Operations | Phases 6-9 | Planned | - |
