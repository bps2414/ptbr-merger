# Phase 5 Research

## Objective

Determine the smallest safe set of changes needed to convert the `v0.4.0` milestone audit from `gaps_found` to passable closeout status without reopening shipped feature work.

## Findings

### 1. The audit gaps are artifact gaps, not behavior gaps

The current milestone audit already concludes that the shipped behavior is present:

- Phase 2 requirements are satisfied through summaries, validation, and UAT.
- Phase 3 requirements are satisfied through summaries and validation, but the phase lacks persisted UAT and standalone verification artifacts.
- Phase 4 requirements are satisfied through summaries, validation, and UAT, but the phase lacks standalone verification and still leaves traceability unchecked in `REQUIREMENTS.md`.

Implication:

- Phase 5 should not touch runtime code unless a verification command proves something unexpectedly broken.
- The main deliverables are planning artifacts that make the evidence legible to the GSD workflow.

### 2. The missing artifact pattern is consistent enough to normalize

Across phases 2-4, the repository already has:

- `*-SUMMARY.md`
- `*-VALIDATION.md`
- sometimes `*-UAT.md`

What is inconsistent is the standalone `*-VERIFICATION.md` layer and, for Phase 3, the missing persisted UAT record.

Implication:

- The fastest path is to standardize `02-VERIFICATION.md`, `03-VERIFICATION.md`, and `04-VERIFICATION.md`.
- Phase 3 also needs `03-UAT.md` to match the same persistence model used by phases 1, 2, and 4.

### 3. Traceability drift is currently localized

`REQUIREMENTS.md` is already checked for:

- `SYNC-01` to `SYNC-03`
- `AUTO-01` to `AUTO-03`
- `SAFE-01`
- `TEST-01`

The stale rows are Phase 4 closeout items:

- `MAN-01`
- `MAN-02`
- `MAN-03`
- `OBS-01`
- `OBS-02`
- `TEST-02`

Implication:

- Phase 5 should explicitly restore these rows to checked state only after adding the missing verification artifacts that justify them.
- The requirements file should be treated as the final reflection of evidence, not the source of truth by itself.

### 4. Re-audit is the correct end-of-phase proof

Because this phase exists only to close milestone audit gaps, its strongest verification is not just file creation. It is a successful rerun of the milestone audit workflow or, at minimum, a no-gap evidence package that makes rerun deterministic.

Implication:

- The last plan should explicitly re-run the milestone audit and update state artifacts based on the result.
- If any residual debt remains, it must be downgraded to non-blocking or captured clearly.

## Recommended Approach

Use two waves:

1. Artifact normalization wave
   - create missing `VERIFICATION.md` files for phases 2-4
   - create missing `03-UAT.md`
   - cite exact evidence from summaries, validation, tests, and existing UAT

2. Traceability and closeout wave
   - align `REQUIREMENTS.md` with the now-documented evidence
   - refresh `STATE.md` and any phase summary references if needed
   - rerun milestone audit and confirm the gap set is closed

## Validation Architecture

This phase is documentation-heavy but still needs executable proof:

- targeted reads of produced verification artifacts
- `pytest` spot checks only if a verification claim needs refreshed evidence
- milestone audit rerun as the final closure command

## Risks

- If the re-audit logic expects stricter artifact naming/content than assumed, Phase 5 may need one revision cycle after the first audit rerun.
- If any Phase 3 evidence is weaker than the summaries imply, the missing `03-UAT.md` could expose a real gap instead of a paperwork gap.

## Conclusion

The phase should stay narrow: normalize evidence, repair traceability, rerun audit, and stop.
