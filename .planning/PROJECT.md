# PTBRMerger

## What This Is

PTBRMerger is a brownfield Python automation pipeline that augments imported 4K movies with PT-BR audio by orchestrating Radarr, qBittorrent, FFmpeg/FFprobe and optional Bazarr lookups. It is built for a local Windows-based media stack where reliability, observability and safe file replacement matter more than raw feature count.

## Core Value

When a 4K movie lacks PT-BR audio, the pipeline must recover a compatible PT-BR source and merge it safely without corrupting or wrongly replacing the original file.

## Requirements

### Validated

- ✓ Detect imported 4K movies from Radarr and inspect streams for native PT-BR audio - existing
- ✓ Search Radarr releases, score PT-BR candidates and bypass directly into qBittorrent - existing
- ✓ Deduplicate qBittorrent injections and prioritize `ptbrmerger` downloads - existing
- ✓ Diagnose sync/runtime compatibility before muxing and validate the final MKV before replacement - existing
- ✓ Persist operational state in queue/history ledgers and expose CLI tooling for status, preflight, webhook refresh and runtime hygiene - existing
- ✓ Cover core orchestration, media integration and API payload drift with automated tests - existing
- ✓ Keep runtime state, logs, caches, and local tooling artifacts out of source control by default - validated in Phase 1
- ✓ Distinguish tracked project artifacts from local operational files through explicit ignore rules and documentation - validated in Phase 1
- ✓ Keep `.planning/` tracked intentionally while preserving local-only config and runtime files - validated in Phase 1
- ✓ Keep PT-BR candidates under evaluation when large runtime divergence still looks recoverable - v0.4.0
- ✓ Classify large-diff sync failures into actionable recoverability categories before discard - v0.4.0
- ✓ Attempt conservative automatic sync recovery before fallback when recoverability evidence supports it - v0.4.0
- ✓ Validate recovered outputs conservatively before any destructive 4K replacement - v0.4.0
- ✓ Allow assisted/manual sync recovery with explicit operator controls and replayable metadata - v0.4.0
- ✓ Expose recovery attempts and outcomes clearly across notifications, queue/history, and operator tooling - v0.4.0
- ✓ Cover recoverable and unrecoverable large-diff sync scenarios with automated tests - v0.4.0

### Active

- **ORCH-01**: Split orchestration responsibilities currently concentrated in `src/trigger.py`
- **ORCH-02**: Preserve trigger behavior while refactoring orchestration boundaries
- **ORCH-03**: Keep trigger-focused automated coverage intact during refactor
- **RANK-01**: Extract Radarr candidate ranking and fallback rules into dedicated modules
- **RANK-02**: Preserve strict/soft/exploratory ranking behavior with focused tests
- **RANK-03**: Reduce ranking-change blast radius on API-client behavior
- **QUAL-01**: Define a single validation entrypoint for test and compile checks
- **QUAL-02**: Make validation repeatable in the local workflow
- **QUAL-03**: Keep contributor docs aligned with the current validation path

### Out of Scope

- Turning PTBRMerger into a hosted web service or multi-user product - current operating model is local automation and the codebase is not shaped for that yet
- Replacing Radarr/qBittorrent/Bazarr with new upstream integrations - the existing ecosystem is the core environment this tool serves
- Large UX work or GUI dashboards - operational CLI and logs are enough for the current stage
- Full DAW-style waveform editing or a general-purpose sync studio - this milestone stays focused on pipeline-grade recovery, not post-production tooling

## Context

The repository already contains substantial brownfield context in `.planning/codebase/`, a detailed operational guide in `README.md`, and recent implementation history through `CHANGELOG.md` up to v0.3.5 on 2026-03-25. The current codebase is functionally mature for a standalone automation tool, with strong local test coverage and recent hardening around retries, snapshots, real-media fixtures, preflight checks and runtime hygiene.

The most recent shipped milestone is `v0.4.0 Sync Recovery`, which added recoverability-aware diagnostics, conservative automatic sync recovery, assisted/manual recovery controls, clearer operational observability, and a normalized verification trail for milestone closeout. The next milestone can now return to maintainability work from a stronger behavioral baseline.

## Constraints

- **Tech stack**: Python 3.11+, FFmpeg/FFprobe, Radarr, qBittorrent and optional Bazarr - existing integrations and tooling already depend on this stack
- **Environment**: Windows-first local runtime - scripts, paths and operator workflow assume this heavily today
- **Behavioral safety**: No regression in final-file validation, torrent cleanup timing or destructive replacement semantics - this is the product's trust boundary
- **Observability**: Queue/history ledgers, logs and notifier flows must remain understandable during refactors - operations depend on them for diagnosis
- **Compatibility**: Existing tests, synthetic media fixtures and API snapshots must remain valid or be intentionally updated - they are the safety net for future work

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep the current codebase map as the brownfield source of truth | `.planning/codebase/` already captures architecture, stack, testing and risks well enough to initialize planning | ✓ Good |
| Treat current product capabilities as validated requirements | The repository already ships and documents these behaviors, so roadmap work should focus on the next milestone instead of rediscovering shipped scope | ✓ Good |
| Make repository hygiene and planning formalization the next milestone entry point | The workspace is operationally noisy and the planning layer was incomplete, which blocks disciplined iteration | ✓ Good |
| Use `.gitignore` + concise README guidance as the repository boundary contract | The repo needed both enforcement and a lightweight explanation that contributors can actually follow | ✓ Good |
| Close `v0.3.5 Hygiene Baseline` after Phase 1 and defer Phases 2-4 | The hygiene milestone was useful on its own, while the follow-up refactors were not committed for immediate execution | ✓ Good |
| Delay product-scope expansion until orchestration and ranking logic are easier to maintain | More features on top of the current hot spots would compound risk faster than value | Pending |
| Prioritize sync recovery over internal refactors for the next milestone | Rare PT-BR candidates are being discarded too early on large runtime mismatches, which hits the core product outcome more directly than the deferred refactors | ✓ Good |

## Shipped Milestone Status

Shipped milestone: `v0.4.0 Sync Recovery` on 2026-03-26.

The repository now has both a cleaner operational boundary and a materially stronger sync-recovery pipeline. Large runtime mismatches are no longer treated as one generic dead end, and operators have an explicit manual path when conservative automation is not enough. The main remaining pressure has shifted back toward maintainability in orchestration, ranking, and validation workflow structure.

## Current Codebase State

**Latest shipped capability set:**
- recoverability-aware sync diagnosis
- conservative automatic sync recovery with post-validation
- assisted/manual recovery CLI with replayable evidence
- operator-visible recovery state across notifier, status, refresh, and history flows

**Known debt after v0.4.0:**
- `src/trigger.py` still carries too much orchestration responsibility
- ranking/fallback logic is still concentrated in places that are harder to evolve safely
- validation commands and contributor workflow still need a cleaner single entrypoint

## Next Milestone Goals

- Extract orchestration boundaries out of `src/trigger.py` without regressing shipped sync recovery behavior
- Isolate ranking and fallback logic so changes stop splashing into unrelated code paths
- Consolidate validation workflow into a repeatable developer path tied to docs and tests

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
*Last updated: 2026-03-26 after completing v0.4.0 Sync Recovery*
