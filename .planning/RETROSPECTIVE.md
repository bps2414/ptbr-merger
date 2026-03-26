# Retrospective

## Milestone: v0.3.5 - Hygiene Baseline

**Shipped:** 2026-03-25
**Phases:** 1 | **Plans:** 3

### What Was Built

- Established a documented tracked-versus-local repository boundary
- Restored ignore rules for runtime files, caches, logs, and local tooling artifacts
- Added concise README guidance for repository hygiene

### What Worked

- Brownfield planning around the codebase map made it easy to scope only the hygiene work that was actually worth doing now
- Keeping Phase 1 narrow prevented maintainability work from ballooning into half-started refactors
- UAT on the git-facing workflow caught the important “does this feel cleaner now?” question instead of only trusting implementation intent

### What Was Inefficient

- Initial roadmap over-scoped the milestone with future refactor phases that were not actually committed to
- Previously tracked `.pyc` artifacts required explicit git index cleanup after ignore rules were restored

### Patterns Established

- Repository hygiene changes should be treated as productized workflow work: audit, enforce, document, verify
- `.planning/` is part of the tracked project system, not disposable local state

### Key Lessons

- If the milestone is really “stop the repo from being noisy”, lock it to that and ship it fast instead of pretending future refactors are part of the same release
- Missing `.gitignore` is not a small annoyance; it distorts every git-facing judgment call until fixed

## Milestone: v0.4.0 - Sync Recovery

**Shipped:** 2026-03-26
**Phases:** 4 | **Plans:** 11

### What Was Built

- Recoverability diagnostics for large runtime mismatches
- Conservative automatic sync recovery with validation-gated acceptance
- Assisted/manual recovery with explicit CLI controls and replayable metadata
- Clearer recovery observability in notifier, status, refresh, and history flows
- Verification closure artifacts that let the milestone audit pass cleanly

### What Worked

- The milestone stayed anchored to the real product pain: false-negative sync rejection on rare PT-BR candidates
- Fixture-backed media tests made recovery changes defensible instead of vibe-based
- A late documentation-only closure phase was enough to turn a technically-finished milestone into an auditable shipped milestone without reopening feature scope

### What Was Inefficient

- Phase closeout artifacts (`UAT`, `VALIDATION`, `VERIFICATION`) were produced inconsistently, which forced a cleanup phase at the end
- The roadmap tooling did not reliably detect the added gap-closure phase, so some orchestration had to be handled manually

### Patterns Established

- Recovery work should move in layers: classify first, recover second, expose outcomes third
- Manual/operator escape hatches are safest when they reuse the same validation boundary as automatic flows
- Milestone audit quality depends as much on disciplined evidence artifacts as on shipped code

### Key Lessons

- If a milestone introduces new operational states, notifier/status/history work is not optional polish; it is part of the actual feature
- Verification artifacts should be treated as first-class deliverables during phase execution, not as paperwork to maybe fix later
- A narrow gap-closure phase can be a legit tool when the product is shipped but the planning trail is still a mess
