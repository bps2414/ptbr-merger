# Phase 4: Assisted Recovery And Outcomes - Research

**Researched:** 2026-03-26
**Domain:** Operator-driven sync recovery for a local FFmpeg-based media pipeline
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Manual recovery must be explicit and operator-invoked, using CLI controls such as `--manual-recovery` and `--force-candidate`; no implicit activation.
- First-version manual controls must stay conservative and limited to specific candidate selection, forced offset, forced edge trim, and reuse of evidence from automatic attempts.
- Manual retries must persist enough metadata for reproducibility, including strategy, supplied parameters, candidate identity, validation reason, failure reason, and preserved artifacts when requested.
- Observability must clearly distinguish unrecoverable structural mismatch, automatic recovery failed, waiting for manual intervention, manual recovery running, manual recovery failed, and manual recovery succeeded.
- Manual mode may force an attempt, but it may not bypass final validation or safe replacement semantics.
- Phase 4 should reuse the existing trigger architecture, queue/history JSON ledgers, and current tooling instead of opening a broad refactor.

### the agent's Discretion
- Whether the explicit manual entrypoint lives entirely in `src/trigger.py` or is partially surfaced through `src/tools/`
- Exact naming of manual outcome statuses and queue metadata fields
- Whether persisted manual request metadata should live only in `queue.json` + `history.json` or also influence compatibility history scoring

### Deferred Ideas (OUT OF SCOPE)
- Any waveform editor, interactive UI, or DAW-style recovery flow
- Forcing acceptance of invalid mux outputs
- Large-scale decomposition of `src/trigger.py` beyond what is necessary to land the operator flow cleanly

</user_constraints>

<research_summary>
## Summary

The current repository already has the minimum building blocks needed for an assisted/manual recovery flow: explicit CLI invocation via `src/trigger.py`, persistent runtime ledgers in `queue.json` and `history.json`, operator-facing messaging in `src/notifier.py`, and refresh/status tools that can already reconstruct state from queue and history. The gap is not missing infrastructure; it is the absence of an explicit operator contract that can carry manual intent, manual parameters, and manual outcomes through the same pipeline safely.

The cleanest approach is to extend the existing orchestration instead of creating a parallel subsystem. Concretely: add an explicit manual request contract to the trigger CLI, normalize that request into a single persisted payload, reuse `run_merger()` with manual overrides for strategy selection, and keep the same validation gate (`analyzer.validate_recovery_attempt()` + `merger.validate_and_replace()`) regardless of whether the attempt was automatic or manual.

Observability should be treated as part of the manual feature, not a follow-up. The queue entry, append-only history, compatibility/group history, Discord status wording, and `src/tools/status.py` / `src/tools/refresh_webhook.py` all need the same vocabulary so operators can tell the difference between "this source is fundamentally wrong" and "this retry recipe did not work yet".

**Primary recommendation:** add a normalized manual recovery request path inside the existing trigger flow, then propagate explicit manual outcome states across notifier, queue/history, and operator tools before finishing with fixture-backed rejection coverage.
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Orchestration and CLI entrypoints | Already anchors the trigger and all tooling |
| FFmpeg / FFprobe | Existing local install | Execute/manual validation of mux attempts | Already used for extraction, trim, mux, and validation |
| pytest | Existing project dependency | Orchestration, notifier, tool, and fixture regressions | Already covers the exact seams Phase 4 will touch |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| JSON runtime ledgers | Existing project convention | Persist manual requests and outcomes | For reproducible retries without adding a database |
| Discord embed notifier | Existing implementation | Operator-facing outcome clarity | For manual pending/running/failed/success wording |
| Synthetic media fixtures | Existing test support | Safe rejection and manual-success proof | For fixture-backed manual recovery regressions |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extending `src/trigger.py` with an explicit request object | Building a separate `manual_recovery.py` workflow first | Cleaner long-term boundary, but unnecessary indirection for this phase |
| Persisting manual metadata in queue/history JSON | Adding a small SQLite database | Better querying, but unjustified complexity for the current single-user/local flow |
| Reusing notifier/status tooling | Building a new manual dashboard | Higher UX ceiling later, but not needed to satisfy operator visibility now |

**Installation:**
```bash
pip install -r requirements.txt
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
```text
src/
|-- trigger.py
|-- notifier.py
|-- queue_manager.py
|-- history_manager.py
|-- sync_intelligence.py
`-- tools/
    |-- status.py
    `-- refresh_webhook.py
```

### Pattern 1: Normalized manual request payload
**What:** Convert CLI flags into one canonical request object before touching orchestration.
**When to use:** Any time the operator wants to force a specific candidate or provide offset/trim hints.
**Example:**
```python
manual_request = {
    "enabled": True,
    "tmdb_id": "939243",
    "candidate_index": 1,
    "force_offset_seconds": -8.4,
    "trim_start_seconds": 0.0,
    "trim_end_seconds": 24.0,
    "reuse_last_recovery": True,
    "preserve_artifacts": True,
}
```

### Pattern 2: Manual attempt reuses the same safety gate
**What:** Manual mode may override strategy selection, but it still ends in the same validation contract as automatic mode.
**When to use:** During `run_merger()` when deciding how to prepare the recovery attempt and whether to accept the output.
**Example:**
```python
recovery_plan = build_manual_plan(...) if manual_request else _build_recovery_plan(...)
recovery_validation = analyzer.validate_recovery_attempt(...)
validation = merger.validate_and_replace(...)
```

### Pattern 3: Outcome vocabulary shared across runtime ledgers and operator surfaces
**What:** Status codes and metadata keys must stay aligned across notifier, queue/history, and tool output.
**When to use:** Whenever a manual attempt is pending, starts, fails, or succeeds.
**Example:**
```python
context["manual_recovery"] = True
context["manual_request_id"] = "manual-939243-20260326T143000Z"
context["manual_status"] = "MANUAL_RECOVERY_PENDING"
```

### Anti-Patterns to Avoid
- **Manual mode as a validation bypass:** letting operator intent skip `validate_recovery_attempt()` or `validate_and_replace()` would break the trust boundary immediately.
- **Free-form metadata blobs with inconsistent keys:** if queue/history/tools all invent their own field names, reproducible retries become a mess.
- **Treating manual failure like structural incompatibility:** `MANUAL_RECOVERY_FAILED` must not collapse into `CUT_MISMATCH` or `RUNTIME_INCOMPATIBLE`, or operators lose the distinction this phase exists to provide.
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Manual state persistence | New state store | Existing `queue.json`, `history.json`, `group_history.json` managers | The runtime already persists operator-visible state safely enough for this phase |
| Notification transport | New webhook client | `src.notifier.py` plus `src.tools.refresh_webhook.py` | Existing embed/update workflow already supports progress and terminal refresh |
| Recovery execution | Separate manual mux pipeline | Existing `run_merger()` + merger/analyzer helpers | Avoids logic drift between automatic and manual safety rules |

**Key insight:** Phase 4 is mostly a contract and observability problem layered on top of working recovery primitives, not a brand-new media-processing problem.
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Manual request cannot be replayed exactly
**What goes wrong:** The operator can force a run once, but the queue/history do not capture enough fields to retry the same attempt later.
**Why it happens:** Only human-readable strings are stored, while concrete parameters stay transient in memory.
**How to avoid:** Persist exact fields for candidate index, supplied offset/trim, reuse flags, request source, artifact retention, and resulting validation/failure reason.
**Warning signs:** A failed manual run can be described, but not reproduced from queue/history output alone.

### Pitfall 2: Tooling still shows generic terminal statuses
**What goes wrong:** `status.py`, refreshed Discord embeds, or group history summarize manual outcomes as generic `FAILED`, `CUT_MISMATCH`, or `SUCCESS`.
**Why it happens:** Production logic changes land in `trigger.py`, but notifier/tools are not updated as part of the same change set.
**How to avoid:** Treat notifier, refresh, queue snapshot, and compatibility history semantics as part of the manual-flow feature.
**Warning signs:** Manual failure and unrecoverable structural mismatch produce indistinguishable operator output.

### Pitfall 3: Manual overrides leak into automatic scoring incorrectly
**What goes wrong:** A manually forced bad attempt penalizes a release/source combo the same way a naturally unrecoverable candidate would.
**Why it happens:** Group-history result buckets are reused without considering manual semantics.
**How to avoid:** Add explicit manual result names and decide deliberately whether they should affect scoring, rather than letting them fall into existing cut/runtime failure sets by accident.
**Warning signs:** Compatibility scoring gets harsher after manual experiments even when the underlying candidate was never proven structurally incompatible.
</common_pitfalls>

## Validation Architecture

- Keep the feedback loop concentrated on four seams: CLI/orchestration (`tests/test_trigger.py`), operator messaging (`tests/test_notifier.py`), runtime tooling (`tests/test_tools.py`), and compatibility history semantics (`tests/test_sync_intelligence.py`).
- Use fixture-backed coverage in `tests/test_media_integration.py` only after the manual request contract and outcome vocabulary are stable; otherwise failures become too broad to diagnose quickly.
- End the phase with the same full gate as the prior milestone work: targeted pytest runs during development, then the full phase suite plus `python -m compileall src tests`.

<sources>
## Sources

### Primary (HIGH confidence)
- `.planning/phases/04-assisted-recovery-and-outcomes/04-CONTEXT.md`
- `.planning/phases/04-assisted-recovery-and-outcomes/04-DISCUSSION-LOG.md`
- `src/trigger.py`
- `src/notifier.py`
- `src/queue_manager.py`
- `src/history_manager.py`
- `src/sync_intelligence.py`
- `src/tools/status.py`
- `src/tools/refresh_webhook.py`
- `tests/test_trigger.py`
- `tests/test_notifier.py`
- `tests/test_tools.py`

### Secondary (MEDIUM confidence)
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/TESTING.md`
- `README.md`

### Tertiary (LOW confidence - needs validation)
- No tertiary sources used
</sources>
