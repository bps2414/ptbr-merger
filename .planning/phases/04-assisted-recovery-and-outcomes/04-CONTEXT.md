# Phase 4 Context: Assisted Recovery And Outcomes

## Objective

Add an operator-controlled recovery path for rare PT-BR candidates that conservative automatic recovery still cannot salvage, while keeping the final validation trust boundary intact.

## Why This Phase Exists

Phase 2 stopped discarding plausible large-diff candidates too early.
Phase 3 proved that conservative automatic recovery can save at least one real-world case, including the Sonic the Hedgehog 3 (2024) case that originally motivated this milestone.

What remains is the operator-controlled path for scenarios where:

- the automatic path preserves a candidate but cannot decide safely on its own
- the operator wants to force a known candidate because it is the only viable PT-BR source
- retrying with explicit parameters such as offset or trim is preferable to editing source code by hand

## Decisions Locked During Discussion

1. Manual entry must be explicit

- Use explicit CLI/operator controls such as `--manual-recovery` and/or `--force-candidate`
- No hidden or automatic activation of manual behavior

2. First manual controls stay conservative

- select a specific candidate
- force offset
- force trim at the start and/or end
- reuse evidence or artifacts from the automatic attempt when available

Out of scope for this phase:

- multi-cut internal surgery
- waveform-editor style recovery
- skipping final validation

3. Manual retries must be reproducible

Persist enough metadata to reproduce what happened:

- strategy used
- parameters supplied
- release/candidate identity
- validation reason
- failure reason
- intermediate artifacts when intentionally preserved

4. Outcomes must stay distinct in observability

The operator must be able to distinguish:

- unrecoverable structural mismatch
- automatic recovery failed
- waiting for manual intervention
- manual recovery running
- manual recovery failed
- manual recovery succeeded

5. Safety boundary remains unchanged

Manual mode can force an attempt.
Manual mode cannot force acceptance of an invalid result.
Replacement of the original 4K still depends on validation and post-check gates.

## Expected Deliverables

- CLI/manual entrypoints for assisted recovery
- persisted manual recovery metadata and artifacts
- notifier/queue/history vocabulary for manual states and outcomes
- automated coverage for safe manual success and safe manual rejection

## Inputs From Previous Phases

- Phase 2 introduced recoverability diagnosis and candidate preservation
- Phase 3 introduced conservative automatic recovery and strategy-aware post-validation
- Real-world validation already proved Sonic the Hedgehog 3 (2024) can be recovered automatically via `edge-trim`

## Open Constraints

- The Discord webhook path is still affected by the local proxy issue (`127.0.0.1:9`), but pipeline behavior itself is functional
- Manual controls should reuse current trigger architecture rather than starting an unrelated refactor here
