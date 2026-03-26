# PTBRMerger

## What This Is

PTBRMerger is a brownfield Python automation pipeline that augments imported 4K movies with PT-BR audio by orchestrating Radarr, qBittorrent, FFmpeg/FFprobe and optional Bazarr lookups. It is built for a local Windows-based media stack where reliability, observability and safe file replacement matter more than raw feature count.

## Core Value

When a 4K movie lacks PT-BR audio, the pipeline must recover a compatible PT-BR source and merge it safely without corrupting or wrongly replacing the original file.

## Requirements

### Validated

- ✓ Detect imported 4K movies from Radarr and inspect streams for native PT-BR audio — existing
- ✓ Search Radarr releases, score PT-BR candidates and bypass directly into qBittorrent — existing
- ✓ Deduplicate qBittorrent injections and prioritize `ptbrmerger` downloads — existing
- ✓ Diagnose sync/runtime compatibility before muxing and validate the final MKV before replacement — existing
- ✓ Persist operational state in queue/history ledgers and expose CLI tooling for status, preflight, webhook refresh and runtime hygiene — existing
- ✓ Cover core orchestration, media integration and API payload drift with automated tests — existing
- ✓ Keep runtime state, logs, caches, and local tooling artifacts out of source control by default — validated in Phase 1
- ✓ Distinguish tracked project artifacts from local operational files through explicit ignore rules and documentation — validated in Phase 1
- ✓ Keep `.planning/` tracked intentionally while preserving local-only config and runtime files — validated in Phase 1

### Active

(No active milestone requirements right now.)

### Out of Scope

- Turning PTBRMerger into a hosted web service or multi-user product — current operating model is local automation and the codebase is not shaped for that yet
- Replacing Radarr/qBittorrent/Bazarr with new upstream integrations — the existing ecosystem is the core environment this tool serves
- Large UX work or GUI dashboards — operational CLI and logs are enough for the current stage

## Context

The repository already contains substantial brownfield context in `.planning/codebase/`, a detailed operational guide in `README.md`, and recent implementation history through `CHANGELOG.md` up to v0.3.5 on 2026-03-25. The current codebase is functionally mature for a standalone automation tool, with strong local test coverage and recent hardening around retries, snapshots, real-media fixtures, preflight checks and runtime hygiene.

The most recent shipped milestone is `v0.3.5 Hygiene Baseline`, which intentionally delivered only repository hygiene work and paused before the deeper refactor phases originally sketched in the first brownfield roadmap. The main product risk is still maintainability drift: `src/trigger.py` and `src/radarr_client.py` carry too much orchestration and heuristic logic, but that work is currently deferred until a future milestone is explicitly started.

## Constraints

- **Tech stack**: Python 3.11+, FFmpeg/FFprobe, Radarr, qBittorrent and optional Bazarr — existing integrations and tooling already depend on this stack
- **Environment**: Windows-first local runtime — scripts, paths and operator workflow assume this heavily today
- **Behavioral safety**: No regression in final-file validation, torrent cleanup timing or destructive replacement semantics — this is the product's trust boundary
- **Observability**: Queue/history ledgers, logs and notifier flows must remain understandable during refactors — operations depend on them for diagnosis
- **Compatibility**: Existing tests, synthetic media fixtures and API snapshots must remain valid or be intentionally updated — they are the safety net for future work

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep the current codebase map as the brownfield source of truth | `.planning/codebase/` already captures architecture, stack, testing and risks well enough to initialize planning | ✓ Good |
| Treat current product capabilities as validated requirements | The repository already ships and documents these behaviors, so roadmap work should focus on the next milestone instead of rediscovering shipped scope | ✓ Good |
| Make repository hygiene and planning formalization the next milestone entry point | The workspace is operationally noisy and the planning layer was incomplete, which blocks disciplined iteration | ✓ Good |
| Use `.gitignore` + concise README guidance as the repository boundary contract | The repo needed both enforcement and a lightweight explanation that contributors can actually follow | ✓ Good |
| Close `v0.3.5 Hygiene Baseline` after Phase 1 and defer Phases 2-4 | The hygiene milestone was useful on its own, while the follow-up refactors were not committed for immediate execution | ✓ Good |
| Delay product-scope expansion until orchestration and ranking logic are easier to maintain | More features on top of the current hot spots would compound risk faster than value | — Pending |

## Current State

Shipped milestone: `v0.3.5 Hygiene Baseline` on 2026-03-25.

The project is currently between milestones. Repository hygiene is back under control, `.planning/` is treated as tracked project state, and future refactor/validation work remains deferred until a new milestone is intentionally opened.

## Next Milestone Goals

- Revisit whether `src/trigger.py` decomposition is still the highest-value maintainability step
- Decide whether ranking extraction or validation workflow should follow next
- Start a fresh milestone only when that scope is actually committed

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition**:
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone**:
1. Full review of all sections
2. Core Value check -> still the right priority?
3. Audit Out of Scope -> reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-25 after v0.3.5 Hygiene Baseline milestone completion*
