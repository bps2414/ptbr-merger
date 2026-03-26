# Phase 03 - Research Notes

## Summary

Phase 3 can build on existing recovery primitives instead of introducing a new sync engine. The current code already supports offset muxing, fingerprint evidence, preserved recoverability metadata, and strict final validation. The missing pieces are a structured automatic recovery ladder, strategy-specific post-checks, and fixture-backed proof that at least one large-diff candidate becomes valid after recovery.

## Findings

### Existing recovery seed already exists in trigger

- `src/trigger.py` already has a narrow automatic offset path:
  - applies `audio_offset_seconds`
  - records offset strategy/outcome
  - validates before replacement
  - fails safely into explicit `OFFSET_SUSPECTED_FAILED`
- This means Phase 3 should extend a known-safe path rather than inventing a separate orchestration model.

### FFmpeg integration is sufficient for conservative recovery

- `src/merger.py` already supports:
  - extract audio without re-encode
  - mux with optional `-itsoffset`
  - final validation + replace
- The likely missing primitive for edge recovery is a helper to trim extracted audio before muxing.
- No evidence suggests Phase 3 needs a third-party sync library; FFmpeg plus existing fingerprinting is enough for the conservative scope agreed in context.

### Validation is the trust boundary and must stay central

- `src/analyzer.validate_final_file()` is already the replacement gate.
- Architecture docs and prior phase context both reinforce that replacement safety is non-negotiable.
- Research conclusion:
  - automatic recovery success must never be inferred from FFmpeg exit code alone
  - Phase 3 needs at least one post-adjustment sync check in addition to final-file validation

### Fingerprint evidence is the best gate for ambiguous recovery

- `src/audio_fingerprint.py` already measures alignment at `head`, `mid`, and `tail`.
- Phase 2 now preserves `AMBIGUOUS_RECOVERABLE` with fingerprint metadata in queue/history.
- Research conclusion:
  - `recoverable` diagnoses can attempt automatic recovery directly
  - `ambiguous` diagnoses should require stronger evidence such as a stable offset anchor or edge-aligned post-check before recovery is considered safe

### Current media corpus proves offset but not edge-trim recovery

- Existing fixtures:
  - `dual_offset_ok` proves automatic offset is viable
  - `dual_cut_mismatch` proves structural mismatch rejection
- Missing fixture:
  - a recoverable edge-divergence case where trimming start/end actually converts a large-diff candidate into a valid output
- Research conclusion:
  - Phase 3 should add at least one fixture-backed recovery case, otherwise `TEST-01` stays under-proven

### History and notifier already have the right extension seams

- `src/notifier.py` already exposes recovery categories and diagnostic metadata.
- `src/sync_intelligence.py` already distinguishes recoverable versus terminal mismatch semantics after Phase 2.
- Phase 3 can extend this vocabulary with strategy-attempt results rather than redesigning observability.

## Planning Implications

1. Start with a conservative recovery ladder:
   - offset
   - edge trimming
2. Keep strategy selection in the existing trigger path unless extraction becomes too ugly.
3. Add explicit post-recovery verification metadata so operator-facing outputs explain what happened.
4. Add a real-media-style fixture for trim-based recovery before calling the phase complete.

## Recommended Validation Loop

- Fast loop:
  - `pytest -q tests/test_trigger.py tests/test_merger.py`
- Recovery coverage loop:
  - `pytest -q tests/test_media_integration.py tests/test_analyzer.py`
- Final gate:
  - `pytest -q tests/test_trigger.py tests/test_merger.py tests/test_media_integration.py tests/test_analyzer.py tests/test_sync_intelligence.py`
  - `python -m compileall src tests`
