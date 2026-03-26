# Phase 2: Recoverability Diagnostics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 02-recoverability-diagnostics
**Areas discussed:** diagnostic boundary, classification model, evidence sources, candidate handling, safety bias

---

## Diagnostic Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Diagnose only | Phase 2 classifies recoverability and routing without attempting recovery yet | ✓ |
| Diagnose + recover | Phase 2 already performs full sync correction attempts | |

**User's choice:** Diagnose only in this phase; leave actual recovery mechanics for the next phase.
**Notes:** The user wants to stop losing candidates due to shallow diagnosis, especially when the mismatch may just be intro/outro differences.

---

## Classification Model

| Option | Description | Selected |
|--------|-------------|----------|
| Rich recoverability categories | Distinguish offset, intro/outro divergence, drift, incompatible cut, and ambiguous recoverable cases | ✓ |
| Keep generic cut mismatch | Preserve the current broad `CUT_MISMATCH` bucket | |

**User's choice:** Rich recoverability categories.
**Notes:** The user specifically called out cases where the movie is being lost for what may only be intro/outro divergence.

---

## Evidence Sources

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing sync evidence | Build on FFprobe/runtime, fingerprint, and current heuristics first | ✓ |
| Introduce new sync stack now | Add new external tooling during Phase 2 | |

**User's choice:** Reuse existing sync evidence.
**Notes:** The user expectation is pragmatic: if the pipeline can tell the candidate is recoverable, later phases can use FFmpeg or existing tooling to try to save it.

---

## Candidate Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve recoverable candidates | Keep likely-recoverable candidates alive for later recovery | ✓ |
| Fallback immediately | Keep current early discard behavior | |

**User's choice:** Preserve recoverable candidates.
**Notes:** The user highlighted real pain from losing the only viable PT-BR candidate because the current flow discards too aggressively.

---

## Safety Bias

| Option | Description | Selected |
|--------|-------------|----------|
| Conservative success, lenient routing | Be permissive about trying recovery later, but conservative about ever marking sync as safe | ✓ |
| Aggressive acceptance | Treat many mismatches as safe enough right away | |

**User's choice:** Conservative success, lenient routing.
**Notes:** The user wants more chances to save the candidate, not reckless acceptance of badly aligned audio.

---

## the agent's Discretion

- Exact enum/category naming for the richer diagnosis vocabulary
- Diagnostic data-shape design for passing recoverability evidence downstream
- Balance between informational and decision-making use of group history

## Deferred Ideas

- Automatic FFmpeg-based recovery work belongs to Phase 3
- Manual/operator-driven recovery flows belong to Phase 4
