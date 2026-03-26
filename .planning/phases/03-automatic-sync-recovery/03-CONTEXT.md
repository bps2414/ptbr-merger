# Phase 3: Automatic Sync Recovery - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Attempt conservative automatic sync recovery for candidates already classified as recoverable, and only keep outputs that still pass strict validation before replacing the original 4K file.

</domain>

<decisions>
## Implementation Decisions

### Recovery Scope
- **D-01:** Phase 3 should start with a conservative recovery ladder: fixed offset first, then edge trimming for intro/outro divergence.
- **D-02:** Phase 3 should not attempt multi-segment timeline surgery, scene-by-scene patching, or aggressive time-stretching; those stay out of scope for automatic recovery.

### Recovery Eligibility
- **D-03:** Candidates marked `recoverable` may enter the automatic recovery path directly.
- **D-04:** Candidates marked `ambiguous` may enter automatic recovery only when fingerprint or equivalent evidence provides an additional anchor strong enough to justify a safe attempt.
- **D-05:** Candidates marked `terminal` must never enter automatic recovery.

### Safety Gates
- **D-06:** Every automatic recovery attempt must pass the existing final-file validation and at least one sync-specific post-adjustment check before replacement is allowed.
- **D-07:** Recovery success must never be inferred solely from FFmpeg completing without error; the output must be proven safe enough to keep.

### Failure Handling
- **D-08:** If automatic recovery fails, the pipeline must record the attempted strategy, evidence, and failure reason explicitly instead of collapsing the result into a generic sync mismatch.
- **D-09:** Failed automatic recovery should preserve enough metadata and intermediate context for later assisted/manual recovery in Phase 4.

### the agent's Discretion
- Exact naming of automatic recovery statuses and result enums
- Whether recovery strategy selection lives entirely in `trigger.py` or is extracted into helper functions during implementation
- The precise threshold mix for allowing ambiguous candidates into an automatic attempt

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition
- `.planning/ROADMAP.md` - defines the goal and success criteria for Phase 3
- `.planning/PROJECT.md` - defines the milestone trust boundary and recovery objective
- `.planning/REQUIREMENTS.md` - defines `AUTO-01`, `AUTO-02`, `AUTO-03`, `SAFE-01`, and `TEST-01`
- `.planning/STATE.md` - records current milestone position and recent validation outcome

### Prior phase context
- `.planning/phases/02-recoverability-diagnostics/02-CONTEXT.md` - locks the recoverability model that Phase 3 must consume
- `.planning/phases/02-recoverability-diagnostics/02-01-SUMMARY.md` - summarizes the diagnosis contract delivered in Phase 2
- `.planning/phases/02-recoverability-diagnostics/02-02-SUMMARY.md` - summarizes trigger preservation and fingerprint routing changes
- `.planning/phases/02-recoverability-diagnostics/02-03-SUMMARY.md` - summarizes status/history taxonomy alignment
- `.planning/phases/02-recoverability-diagnostics/02-UAT.md` - confirms the Phase 2 behavior on a real Sonic candidate

### Recovery path code
- `src/trigger.py` - current orchestration, candidate preservation, offset path, and fallback behavior
- `src/merger.py` - current extraction, mux, and replace flow that Phase 3 will build on
- `src/analyzer.py` - validation and diagnosis metadata that gate recovery
- `src/audio_fingerprint.py` - fingerprint evidence source for offsets and ambiguity resolution
- `src/notifier.py` - operator-facing vocabulary for recovery attempts and outcomes
- `src/sync_intelligence.py` - compatibility history semantics that should reflect recovery results
- `src/config.py` - current diagnostics and fingerprint thresholds, plus future recovery knobs

### Test coverage
- `tests/test_trigger.py` - orchestration seam for automatic recovery behavior
- `tests/test_analyzer.py` - validation contract and sync classification expectations
- `tests/test_media_integration.py` - fixture-backed path for proving large-diff recovery can become valid
- `tests/test_sync_intelligence.py` - compatibility history regression surface

### Codebase guidance
- `.planning/codebase/ARCHITECTURE.md` - orchestration/data-flow overview
- `.planning/codebase/CONCERNS.md` - risks around sync, validation, and replacement safety
- `.planning/codebase/TESTING.md` - current testing strategy and recommended suites
- `.planning/codebase/CONVENTIONS.md` - repository conventions relevant to implementation shape

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src.trigger.py` already has a narrow automatic offset path with validation-aware failure handling, which is the natural seed for a broader recovery ladder.
- `src.merger.mux_audio()` already supports `audio_offset_seconds`, so offset-based recovery can stay within the current FFmpeg integration.
- `src.audio_fingerprint.fingerprint_sync()` already provides multi-position evidence that can help choose or reject a recovery strategy.
- `src.analyzer.validate_final_file()` already guards final replacement and should remain the non-negotiable trust boundary.

### Established Patterns
- Recovery-relevant metadata is already threaded through the shared `context` dict and recorded into queue/history/group history.
- `src.trigger.py` owns orchestration decisions, retries, and fallback timing today, so Phase 3 can extend that path tactically without inventing a new orchestration surface.
- Existing tests prefer mocked orchestration plus selected real-media fixtures; that is still the right verification seam here.

### Integration Points
- `src.trigger.py` must route preserved candidates into concrete automatic recovery attempts before fallback.
- `src.merger.py` likely needs helper support for edge trimming or adjusted mux inputs beyond plain offset.
- `src.notifier.py`, queue metadata, and history outputs must expose which strategy was attempted and why it passed or failed.
- `tests/test_trigger.py` and `tests/test_media_integration.py` are the key places to prove at least one large-diff candidate becomes valid after recovery.

</code_context>

<specifics>
## Specific Ideas

- The Sonic real-world case confirmed that a 141.179s mismatch can now stay alive as `AMBIGUOUS_RECOVERABLE`; Phase 3 is where the pipeline should actually try to save that kind of candidate automatically.
- The user explicitly wants the automatic path to cover the common “just intro/outro/logo difference” cases that currently waste rare PT-BR releases.
- The automatic path should feel strict and boring, not adventurous; success should mean “safe enough to trust,” not “FFmpeg managed to output a file.”

</specifics>

<deferred>
## Deferred Ideas

- Operator-forced recovery parameters, candidate forcing, and manual reruns - belongs to Phase 4
- Aggressive stretch/resample workflows or multi-cut reconstruction - out of scope for this automatic phase
- Large trigger refactors unrelated to shipping recovery safely - still deferred

</deferred>

---

*Phase: 03-automatic-sync-recovery*
*Context gathered: 2026-03-26*
