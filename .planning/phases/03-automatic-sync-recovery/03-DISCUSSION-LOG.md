# Phase 3: Automatic Sync Recovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 03-automatic-sync-recovery
**Areas discussed:** Recovery Scope, Recovery Eligibility, Safety Gates, Failure Handling

---

## Recovery Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Offset only | Restrict automation to fixed offset cases | |
| Conservative ladder | Fixed offset first, then edge trimming for intro/outro divergence | ✓ |
| Aggressive recovery | Include complex multi-cut or stretch-based repair paths | |

**User's choice:** Accepted recommended default.
**Notes:** Automatic recovery should start conservatively and avoid timeline surgery.

---

## Recovery Eligibility

| Option | Description | Selected |
|--------|-------------|----------|
| Recoverable only | Only `recoverable` diagnoses get an automatic attempt | |
| Recoverable + evidence-backed ambiguous | `recoverable` enters directly; `ambiguous` requires stronger evidence | ✓ |
| All non-terminal cases | Anything not terminal is attempted automatically | |

**User's choice:** Accepted recommended default.
**Notes:** Ambiguous cases need additional evidence before automatic recovery is allowed.

---

## Safety Gates

| Option | Description | Selected |
|--------|-------------|----------|
| FFmpeg success only | Trust successful command execution as enough | |
| Validation gate | Require full validation and sync-specific post-checks before replacement | ✓ |
| Manual review gate | Always require human confirmation after automatic recovery | |

**User's choice:** Accepted recommended default.
**Notes:** Automatic recovery remains subordinate to the final validation trust boundary.

---

## Failure Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Generic failure | Collapse failures back into generic sync mismatch | |
| Specific recovery outcome | Record strategy attempted, evidence, and failure reason for later assisted follow-up | ✓ |
| Immediate deletion | Discard failed recovery candidates with minimal trace | |

**User's choice:** Accepted recommended default.
**Notes:** Failed attempts must leave enough breadcrumbs for Phase 4 manual recovery.

---

## the agent's Discretion

- Exact status/result naming for automatic recovery attempt outcomes
- Tactical code organization for strategy selection helpers
- Threshold details for admitting ambiguous candidates into automatic recovery

## Deferred Ideas

- Manual forced recovery and operator knobs - Phase 4
- Aggressive stretch or multi-cut repair - out of scope for Phase 3
