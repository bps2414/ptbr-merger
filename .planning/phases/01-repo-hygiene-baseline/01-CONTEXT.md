# Phase 1: Repo Hygiene Baseline - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Re-establish a sane repository boundary between tracked source/planning artifacts and local operational outputs. This phase covers ignore rules, local artifact handling, and concise documentation of that boundary; it does not add new product capabilities or reorganize the runtime architecture itself.

</domain>

<decisions>
## Implementation Decisions

### Tracking Policy
- **D-01:** The repository must track only source and intentional project docs: `src/`, `tests/`, `scripts/`, `README.md`, `CHANGELOG.md`, `requirements.txt`, `config.example.yml`, and `.planning/`.
- **D-02:** Local-only files must not be versioned: `config.yml`, `queue.json`, `retry_queue.json`, `history.json`, `group_history.json`, and `ptbrmerger.log`.
- **D-03:** Generated caches and Python build artifacts must be ignored by default, including `__pycache__/`, `.pytest_cache/`, and `*.pyc`.

### Cleanup Scope
- **D-04:** This phase should do a complete cleanup with care: stop future pollution and also clean current workspace noise where safe.
- **D-05:** `config.yml` must be preserved as a local operator file and must not be deleted as part of cleanup.
- **D-06:** Runtime JSON ledgers should remain available as local operational files; the phase should remove them from source-control noise without blindly deleting operator data.

### Local Tooling Artifacts
- **D-07:** Treat `.codex/`, `.codex-repro-readonly/`, `.codex-repro-write/`, `.runtime-archive/`, `tmp/`, and `get-shit-done-cc-1.28.0.tgz` as local tooling/dev artifacts and ignore them.
- **D-08:** Do not spend this phase reorganizing those local tooling paths; the goal is hygiene, not workspace redesign.

### Documentation Boundary
- **D-09:** Add a short pragmatic repository-hygiene section to `README.md` documenting what is tracked versus local-only.
- **D-10:** Do not introduce extra formal documentation beyond the README and planning artifacts already created.

### the agent's Discretion
- Exact `.gitignore` pattern structure and grouping
- Whether to add small comments inside `.gitignore` for readability
- Precise wording and placement of the hygiene section in `README.md`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition
- `.planning/ROADMAP.md` — defines the scope, goal, and success criteria for Phase 1
- `.planning/PROJECT.md` — defines brownfield constraints, active requirements, and repository-maintainability priorities
- `.planning/REQUIREMENTS.md` — defines `HYGN-01`, `HYGN-02`, and `HYGN-03`
- `.planning/STATE.md` — records the current project position and existing blockers

### Codebase guidance
- `.planning/codebase/CONCERNS.md` — documents repository hygiene and runtime artifact risks already identified
- `.planning/codebase/CONVENTIONS.md` — captures current configuration and operational conventions relevant to local files
- `README.md` — current operational documentation that will receive the hygiene clarification

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config.example.yml`: already acts as the tracked contract for local configuration and should remain the canonical example file
- `.planning/`: now established as tracked project-planning state and should stay part of the repository boundary

### Established Patterns
- Runtime state is intentionally file-based at repository root via `queue.json`, `retry_queue.json`, `history.json`, `group_history.json`, and `ptbrmerger.log`
- Operator configuration is local-first through `config.yml` with environment-variable overrides
- The project is actively used as both code repo and runtime workspace, so hygiene changes must protect operator data instead of assuming a clean dev-only sandbox

### Integration Points
- `.gitignore` must become the primary enforcement point for the tracked/local boundary
- `README.md` must explain the local-vs-versioned split in the operational docs already used by contributors/operators
- Existing runtime files in the repository root need safe handling during cleanup because they reflect real operational state

</code_context>

<specifics>
## Specific Ideas

- Keep `.planning/` tracked as an official project artifact rather than treating it as disposable local state
- Solve the root problem first: make `git status` useful again before touching deeper refactors in later phases
- Cleanup should be "complete with care": strong enough to remove noise, careful enough not to nuke local operator data

</specifics>

<deferred>
## Deferred Ideas

- Reorganizing local tooling directories into a cleaner workspace layout — explicitly deferred; Phase 1 only ignores them
- Any new product capabilities or runtime-behavior changes — outside the hygiene boundary

</deferred>

---

*Phase: 01-repo-hygiene-baseline*
*Context gathered: 2026-03-25*
