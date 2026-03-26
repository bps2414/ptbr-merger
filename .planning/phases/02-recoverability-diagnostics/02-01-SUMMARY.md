# Plan 02-01 Summary

## Outcome

Expanded the sync diagnosis contract so large runtime mismatches are classified by recoverability instead of collapsing into a generic terminal rejection.

## Delivered

- `src/analyzer.py`
  - Added `recoverability`, `terminal`, `preserve_candidate`, and `recovery_reason` to the diagnosis payload.
  - Split diagnosis outcomes into `SYNC_OK`, `OFFSET_SUSPECTED`, `INTRO_OUTRO_DIVERGENCE`, `AMBIGUOUS_RECOVERABLE`, `CUT_MISMATCH`, and `RUNTIME_INCOMPATIBLE`.
- `src/config.py`
  - Added diagnostics thresholds for edge-difference and ambiguous-recoverable runtime gaps.
- `tests/test_analyzer.py`
  - Locked the taxonomy with unit coverage for recoverable, ambiguous, offset, and terminal paths.

## Verification

- `pytest -q tests/test_analyzer.py`
