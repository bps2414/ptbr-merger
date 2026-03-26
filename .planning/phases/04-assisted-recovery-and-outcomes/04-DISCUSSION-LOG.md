# Phase 4 Discussion Log

Date: 2026-03-26
Phase: 4 - Assisted Recovery And Outcomes

## Summary

The discussion confirmed that Phase 4 should focus on explicit operator-controlled recovery for rare PT-BR candidates that still cannot be resolved automatically.

## Accepted Decisions

- Manual mode must be explicitly invoked rather than inferred automatically
- First-version manual controls should stay conservative:
  - force candidate selection
  - force offset
  - force trim on edges
  - reuse prior evidence/artifacts
- All manual attempts must persist enough metadata for reproducible retries
- Notifications, queue state, and history must distinguish manual failures from unrecoverable structural mismatches
- Manual mode must not bypass final validation or safe replacement rules

## Rationale

This preserves the same trust boundary established in Phase 3 while giving the operator a controlled escape hatch for “this candidate or nothing” cases.

## Outcome

Phase 4 context approved and ready for planning.
