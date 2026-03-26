# Roadmap: PTBRMerger

## Overview

The active roadmap now targets sync recovery for high-value PT-BR candidates that currently fail fast on large runtime mismatches. The milestone balances conservative automatic recovery with assisted/manual operator controls, while preserving the validation trust boundary.

## Milestones

- ✓ **v0.3.5 Hygiene Baseline** - Phase 1 only (shipped 2026-03-25)
- 🚧 **v0.4.0 Sync Recovery** - Phases 2-5 (gap closure in progress)

## Active Milestone: v0.4.0 Sync Recovery

**4 phases** | **14 requirements mapped** | Gap closure in progress

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 2 | Recoverability Diagnostics | Stop discarding large-diff candidates before the pipeline can classify whether they are still recoverable | SYNC-01, SYNC-02, SYNC-03 | 4 |
| 3 | Automatic Sync Recovery | Attempt conservative automatic recovery and keep only outputs that pass safety gates | AUTO-01, AUTO-02, AUTO-03, SAFE-01, TEST-01 | 5 |
| 4 | Assisted Recovery And Outcomes | Add operator-controlled recovery paths plus clear observability for retries, failures and final decisions | MAN-01, MAN-02, MAN-03, OBS-01, OBS-02, TEST-02 | 5 |
| 5 | Verification Closure And Traceability | Close missing UAT/verification artifacts and align milestone traceability so the audit can pass cleanly | MAN-01, MAN-02, MAN-03, OBS-01, OBS-02, TEST-02 | 4 |

### Phase Details

**Phase 2: Recoverability Diagnostics**
Goal: classify large runtime mismatches well enough to decide whether a candidate deserves recovery attempts instead of immediate rejection.
Requirements: SYNC-01, SYNC-02, SYNC-03
Success criteria:
1. Large-diff candidates no longer jump straight from duration mismatch to terminal discard without a recoverability decision.
2. Diagnosis output distinguishes at least fixed offset, drift suspicion, alternate cut/runtime incompatibility, and unresolved ambiguity.
3. Trigger/fallback flow can branch on recoverability instead of treating every large mismatch as the same failure.
4. Automated tests cover recoverable-versus-unrecoverable diagnosis decisions for large runtime gaps.

**Phase 3: Automatic Sync Recovery**
Goal: attempt safe automatic recovery for recoverable candidates and accept them only when validation supports the result.
Requirements: AUTO-01, AUTO-02, AUTO-03, SAFE-01, TEST-01
Success criteria:
1. Recoverable candidates can go through an automatic recovery path before fallback discard.
2. Recovery strategy output records what was attempted and with which measurable parameters.
3. Recovered mux outputs must still pass existing or strengthened validation gates before replacement.
4. Failed automatic recovery reports a specific reason instead of collapsing into a generic sync mismatch.
5. Automated coverage proves at least one large-diff candidate can become valid after recovery.

**Phase 4: Assisted Recovery And Outcomes**
Goal: let the operator insist on a rare candidate with reproducible manual controls and clear visibility into what happened.
Requirements: MAN-01, MAN-02, MAN-03, OBS-01, OBS-02, TEST-02
Success criteria:
1. The operator can explicitly re-run or force a chosen candidate through assisted/manual recovery without editing source code.
2. Manual recovery parameters and intermediate artifacts are persisted clearly enough for reproducible retries.
3. Notifications, queue/history and fallback reasons show whether the candidate was unrecoverable or merely failed the current recovery attempt.
4. Manual/assisted failures still preserve safe cleanup and replacement semantics.
5. Automated coverage proves unrecoverable large-diff candidates are still rejected safely after the new flows exist.

**Phase 5: Verification Closure And Traceability**
Goal: close the formal audit gaps left after implementation by creating the missing verification artifacts, backfilling the missing UAT coverage record, and aligning milestone traceability with the evidence already produced.
Requirements: MAN-01, MAN-02, MAN-03, OBS-01, OBS-02, TEST-02
Gap Closure: closes milestone audit gaps for missing `03-UAT.md`, missing `02/04-VERIFICATION.md` family artifacts, and stale requirement checkboxes/phase mapping.
Success criteria:
1. Phase 3 has a persisted UAT/verification trail matching its shipped automatic-recovery behavior.
2. Phase 4 has a standalone verification artifact that cites the green validation and UAT evidence.
3. Milestone traceability reflects the current evidence instead of leaving delivered Phase 4 requirements unchecked.
4. Re-running `$gsd-audit-milestone` can pass without opening new product-scope work.

## Archived Milestone

<details>
<summary>✓ v0.3.5 Hygiene Baseline - SHIPPED 2026-03-25</summary>

- [x] Phase 1: Repo Hygiene Baseline (3/3 plans) - completed 2026-03-25

</details>

Archived details: `.planning/milestones/v0.3.5-ROADMAP.md`

## Deferred Candidate Work

- Trigger decomposition - originally planned as Phase 2, deferred before execution
- Ranking domain extraction - originally planned as Phase 3, deferred before execution
- Validation workflow - originally planned as Phase 4, deferred before execution

## Progress

| Milestone | Scope | Status | Completed |
|-----------|-------|--------|-----------|
| v0.3.5 Hygiene Baseline | Phase 1 only | Complete | 2026-03-25 |
| v0.4.0 Sync Recovery | Phases 2-5 | Gap closure in progress | - |
