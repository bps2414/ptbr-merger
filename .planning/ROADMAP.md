# Roadmap: PTBRMerger

## Overview

The active roadmap now targets operator-guided local usage. The product already has strong recovery behavior, but too much of that power still depends on raw terminal knowledge. This milestone makes the system safer and more approachable for non-technical operation without jumping straight to a full dashboard.

## Milestones

- ✓ **v0.3.5 Hygiene Baseline** - Phase 1 only (shipped 2026-03-25)
- ✓ **v0.4.0 Sync Recovery** - Phases 2-5 (shipped 2026-03-26)
- 🚧 **v0.4.5 Post-Format Recovery Web Mode** - Phases 6-9 (planned)

## Archived Milestones

<details>
<summary>✓ v0.4.0 Sync Recovery - SHIPPED 2026-03-26</summary>

- [x] Phase 2: Recoverability Diagnostics (3/3 plans) - completed 2026-03-25
- [x] Phase 3: Automatic Sync Recovery (3/3 plans) - completed 2026-03-26
- [x] Phase 4: Assisted Recovery And Outcomes (3/3 plans) - completed 2026-03-26
- [x] Phase 5: Verification Closure And Traceability (2/2 plans) - completed 2026-03-26

</details>

Archived details: `.planning/milestones/v0.4.0-ROADMAP.md`

<details>
<summary>✓ v0.3.5 Hygiene Baseline - SHIPPED 2026-03-25</summary>

- [x] Phase 1: Repo Hygiene Baseline (3/3 plans) - completed 2026-03-25

</details>

Archived details: `.planning/milestones/v0.3.5-ROADMAP.md`

## Active Milestone: v0.4.5 Post-Format Recovery Web Mode

**4 phases** | **12 requirements mapped** | All covered ✓

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|------------------|
| 6 | Local Web Launcher | Start a localhost recovery surface with one Windows launcher and no Node/React dependency | OPS-01, OPS-02 | 4 |
| 7 | Web Doctor And Workspace | Show manual-vs-automation readiness and create local input/output/report/recipe folders | DOC-01, DOC-02, DOC-03 | 4 |
| 8 | Manual Recovery Web Flow | Let the operator inspect two local MKVs, review a safe plan, and generate a new output file without replacing the original | REC-UX-01, REC-UX-02, REC-UX-03, SAFE-OPS-02 | 4 |
| 9 | Reports, Recipes, And Recovery Docs | Save human-readable reports and privacy-safe recipes, then document the post-format path in Portuguese | GUIDE-01 | 3 |

### Phase Details

**Phase 6: Local Web Launcher**
Goal: give the operator one Windows launcher that opens the localhost recovery surface without requiring Node, React tooling or external services.
Requirements: OPS-01, OPS-02
Success criteria:
1. A user can run `START_PTBRMERGER.bat` from Windows.
2. The server binds only to `127.0.0.1:8787`.
3. The browser opens the local recovery UI.
4. The launcher avoids the Microsoft Store `python.exe` alias when a real Python is available.

**Phase 7: Web Doctor And Workspace**
Goal: help the operator understand local blockers early and create a safe local workspace for manual recovery.
Requirements: DOC-01, DOC-02, DOC-03
Success criteria:
1. The UI separates manual readiness from full Radarr/qBittorrent automation readiness.
2. Missing external services do not block the two-file manual mode.
3. The workspace exposes `input/`, `output/`, `workdir/`, `reports/` and `recipes/`.
4. FFmpeg/FFprobe readiness is visible and actionable.

**Phase 8: Manual Recovery Web Flow**
Goal: make two-file manual recovery usable by someone who understands the intent but not the raw trigger syntax.
Requirements: REC-UX-01, REC-UX-02, REC-UX-03, SAFE-OPS-02
Success criteria:
1. The operator can inspect a target MKV and a PT-BR source MKV through the browser.
2. Invalid files, missing files and non-PT-BR sources are rejected before execution begins.
3. The user reviews a server-side plan before the run.
4. The generated MKV is written under `output/` and the original is never replaced.

**Phase 9: Reports, Recipes, And Recovery Docs**
Goal: make the web recovery path discoverable and preserve local evidence for repeatable manual recovery.
Requirements: GUIDE-01
Success criteria:
1. README and operator docs describe the local web workflow in Portuguese.
2. Entry scripts/shortcuts match the documented commands.
3. Reports and recipes are saved locally without embedding media, magnets, trackers or credentials.

## Deferred Candidate Work

- Trigger decomposition - originally planned as Phase 2, deferred before execution
- Ranking domain extraction - originally planned as Phase 3, deferred before execution
- Validation workflow - originally planned as Phase 4, deferred before execution

## Progress

| Milestone | Scope | Status | Completed |
|-----------|-------|--------|-----------|
| v0.3.5 Hygiene Baseline | Phase 1 only | Complete | 2026-03-25 |
| v0.4.0 Sync Recovery | Phases 2-5 | Complete | 2026-03-26 |
| v0.4.5 Post-Format Recovery Web Mode | Phases 6-9 | Planned | - |
