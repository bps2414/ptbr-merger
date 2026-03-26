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
