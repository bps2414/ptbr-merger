# Phase 2: Recoverability Diagnostics - Research

**Researched:** 2026-03-25
**Domain:** Sync recoverability diagnosis for local FFmpeg-based media automation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Phase 2 must separate "diagnose recoverability" from "attempt recovery" so downstream phases can apply recovery strategies without re-litigating sync classification.
- Large runtime mismatch must no longer trigger immediate fallback/discard solely from duration delta; diagnosis must complete first.
- The diagnosis output must distinguish at least these outcomes: fixed offset candidate, intro/outro-only divergence, drift suspicion, structurally incompatible alternate cut, and unresolved-but-recoverable ambiguity.
- Existing `CUT_MISMATCH` behavior should be decomposed into more actionable categories rather than remaining a generic terminal bucket.
- In ambiguous cases, the system should prefer "recoverable/inconclusive" over premature rejection, while still keeping success criteria conservative.
- Phase 2 should build on the current evidence sources already in the codebase: ffprobe/runtime deltas, runtime-oficial heuristics, multi-position audio fingerprinting, and compatibility history where helpful.
- Phase 2 should not introduce a new external sync engine; diagnosis should stay within the existing FFmpeg/FFprobe and fingerprint ecosystem already used by the project.
- When diagnosis indicates plausible recoverability, the candidate must be preserved and annotated for later recovery instead of immediately triggering fallback.
- Diagnosis metadata must be rich enough for later phases to know why a candidate was preserved, including category, confidence, measured offsets or anchors, and why the case is not yet terminal.
- Phase 2 must preserve the product trust boundary: diagnostic leniency is allowed for routing, but not for falsely marking a candidate as merge-safe.
- A clearly incompatible result must still terminate the candidate decisively; only plausible recovery scenarios get the benefit of the doubt.

### the agent's Discretion
- Exact naming of new diagnosis categories and result enums
- Whether to enrich the existing diagnosis dict versus introducing a dedicated typed structure
- How much group-history evidence should influence recoverability versus remaining informational only

### Deferred Ideas (OUT OF SCOPE)
- Implementing the actual automatic recovery mechanics with FFmpeg offset/cut operations
- Exposing operator-driven manual retry/force flows
- Broader refactors of `src/trigger.py` unrelated to sync recoverability

</user_constraints>

<research_summary>
## Summary

The existing code already has the right raw ingredients for smarter sync diagnosis: duration/runtime heuristics in `src/analyzer.py`, multi-position audio evidence in `src/audio_fingerprint.py`, prior compatibility memory in `src/sync_intelligence.py`, and orchestrated fallback control in `src/trigger.py`. The main gap is not missing tooling; it is collapsing too many situations into terminal `CUT_MISMATCH` behavior before those evidence sources can express recoverability.

The standard approach for this phase is to introduce a richer diagnostic taxonomy and carry a structured recoverability decision through the orchestration layer. That means `diagnose_sync()` should stop answering only "safe or dead" and instead answer "safe, recoverable, ambiguous, or structurally incompatible" with evidence attached. `run_merger()` then branches on those states without yet attempting the full recovery mechanics.

The strongest implementation path is evolutionary rather than revolutionary: extend the current diagnosis dict, keep FFmpeg/FFprobe and fingerprint as the evidence stack, preserve existing validation conservatism, and add test coverage around recoverable-versus-terminal routing. This gives Phase 3 a clean handoff for automatic recovery without forcing Phase 2 to solve mux correction itself.

**Primary recommendation:** expand the sync diagnosis contract first, then route trigger/fallback behavior off explicit recoverability states instead of raw duration mismatch outcomes.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Orchestration and diagnostics | Already anchors the whole project and test harness |
| FFprobe via FFmpeg | Existing local install | Runtime and stream metadata evidence | Already used in `src.analyzer.py` and avoids new dependencies |
| NumPy | Existing project dependency | FFT correlation for audio fingerprinting | Already powers multi-position sync evidence in `src.audio_fingerprint.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | Existing project dependency | Unit and integration verification | For every diagnosis and routing regression in this phase |
| Synthetic media fixtures | Existing test support | Realistic sync/cut fixture coverage | When validating recoverable versus incompatible cases end-to-end |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extending current diagnosis dict | New diagnostic subsystem/module now | Cleaner abstraction long-term, but too much refactor risk for a phase focused on behavior change |
| Existing fingerprint heuristics | External sync libraries or subtitle-aligner style tooling | More power later, but unnecessary complexity for a diagnosis-only phase |

**Installation:**
```bash
pip install -r requirements.txt
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```
src/
|-- analyzer.py
|-- audio_fingerprint.py
|-- trigger.py
|-- notifier.py
|-- sync_intelligence.py
`-- config.py
```

### Pattern 1: Evidence-first diagnosis object
**What:** Return a structured diagnosis payload that separates classification, recoverability, and evidence.
**When to use:** Anytime the orchestration layer needs to decide whether to proceed, preserve, retry, or discard a candidate.
**Example:**
```python
diagnosis = {
    "sync_ok": False,
    "category": "INTRO_OUTRO_DIVERGENCE",
    "recoverability": "recoverable",
    "terminal": False,
    "diff": diff,
    "offset_estimate": offset_estimate,
    "offset_confidence": offset_confidence,
}
```

### Pattern 2: Orchestration routed by recoverability state
**What:** `src.trigger.py` should branch on explicit diagnosis semantics rather than infer meaning from one or two category names.
**When to use:** Before fallback, queue failure recording, notification emission, and retry eligibility.
**Example:**
```python
if diagnosis["sync_ok"]:
    proceed_to_stream_check()
elif diagnosis["recoverability"] in {"recoverable", "ambiguous"}:
    preserve_candidate_for_recovery()
else:
    mark_terminal_failure_and_fallback()
```

### Anti-Patterns to Avoid
- **Duration-only terminal decisions:** Large runtime delta alone is not enough to prove the candidate is unrecoverable.
- **Conflating operator status with control flow:** Human-readable status names should not be the only source of routing semantics in `src.trigger.py`.
- **Skipping evidence persistence:** If recoverability is inferred but the why is not stored, later phases cannot act confidently on the candidate.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Runtime metadata | Custom container parser | Existing FFprobe-based helpers in `src.analyzer.py` | Container edge cases are already delegated safely |
| Audio alignment evidence | New waveform engine | Existing FFT-based `fingerprint_sync()` | Current implementation already samples head/mid/tail and is test-covered |
| Compatibility memory | New scoring database | Existing `GroupHistoryManager` and JSON history | Phase 2 only needs lightweight historical hints, not a persistence redesign |

**Key insight:** the project already owns the essential primitives; the missing value is better classification and routing, not a brand-new sync stack.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Recoverability names without routing semantics
**What goes wrong:** New categories get added, but `src.trigger.py` still treats them like old `CUT_MISMATCH` behavior.
**Why it happens:** Status vocabulary changes without updating the control-flow contract.
**How to avoid:** Add explicit recoverability/terminal fields or equivalent normalized helpers, then route off those.
**Warning signs:** New diagnosis tests pass while trigger tests still fall back immediately on the same candidate.

### Pitfall 2: Fingerprint evidence over-trusted for structural mismatch
**What goes wrong:** A noisy or partial fingerprint result gets treated as proof that the candidate is recoverable.
**Why it happens:** Confidence, spread, and edge-only divergence are collapsed into one optimistic branch.
**How to avoid:** Keep ambiguous/inconclusive distinct from confidently recoverable, and preserve the candidate without pretending it is safe yet.
**Warning signs:** Cases with low-confidence or conflicting offsets bypass terminal handling too easily.

### Pitfall 3: New categories break observability and history
**What goes wrong:** Notifications, queue history, or group history store stale category names or misleading summaries.
**Why it happens:** Diagnosis changes land in `src/analyzer.py` first, but downstream taxonomy and tests are not updated together.
**How to avoid:** Treat notifier strings, queue failure statuses, and history result codes as part of the same change set.
**Warning signs:** Operator messages still say generic `SYNC_MISMATCH` while the code internally uses richer diagnosis states.
</common_pitfalls>

## Validation Architecture

- Focus this phase on fast feedback over three seams: unit diagnosis (`tests/test_analyzer.py`), orchestration routing (`tests/test_trigger.py`), and fixture-backed media behavior (`tests/test_media_integration.py`).
- Add targeted tests for new recoverability categories before broad integration assertions, so failures isolate whether the bug is in diagnosis or routing.
- Keep `python -m compileall src tests` in the final verification path because diagnosis changes will touch several cross-imported modules.

<sources>
## Sources

### Primary (HIGH confidence)
- `.planning/phases/02-recoverability-diagnostics/02-CONTEXT.md`
- `src/analyzer.py`
- `src/audio_fingerprint.py`
- `src/trigger.py`
- `src/sync_intelligence.py`
- `tests/test_analyzer.py`
- `tests/test_trigger.py`
- `tests/test_media_integration.py`
- `tests/test_sync_intelligence.py`

### Secondary (MEDIUM confidence)
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/CONCERNS.md`
- `.planning/codebase/TESTING.md`

### Tertiary (LOW confidence - needs validation)
- No tertiary sources used
</sources>
