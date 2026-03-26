# Phase 2: Recoverability Diagnostics - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Classify large runtime mismatches well enough to decide whether a PT-BR candidate should proceed to recovery attempts or be rejected as structurally incompatible. This phase improves diagnosis and routing only; it does not yet implement the full automatic recovery flow itself.

</domain>

<decisions>
## Implementation Decisions

### Diagnostic Boundary
- **D-01:** Phase 2 must separate "diagnose recoverability" from "attempt recovery" so downstream phases can apply recovery strategies without re-litigating sync classification.
- **D-02:** Large runtime mismatch must no longer trigger immediate fallback/discard solely from duration delta; diagnosis must complete first.

### Classification Model
- **D-03:** The diagnosis output must distinguish at least these outcomes: fixed offset candidate, intro/outro-only divergence, drift suspicion, structurally incompatible alternate cut, and unresolved-but-recoverable ambiguity.
- **D-04:** Existing `CUT_MISMATCH` behavior should be decomposed into more actionable categories rather than remaining a generic terminal bucket.
- **D-05:** In ambiguous cases, the system should prefer "recoverable/inconclusive" over premature rejection, while still keeping success criteria conservative.

### Evidence Sources
- **D-06:** Phase 2 should build on the current evidence sources already in the codebase: ffprobe/runtime deltas, runtime-oficial heuristics, multi-position audio fingerprinting, and compatibility history where helpful.
- **D-07:** This phase should not introduce a new external sync engine; diagnosis should stay within the existing FFmpeg/FFprobe and fingerprint ecosystem already used by the project.

### Candidate Handling
- **D-08:** When diagnosis indicates plausible recoverability, the candidate must be preserved and annotated for later recovery instead of immediately triggering fallback.
- **D-09:** Diagnosis metadata must be rich enough for later phases to know why a candidate was preserved, including category, confidence, measured offsets or anchors, and why the case is not yet terminal.

### Safety Bias
- **D-10:** Phase 2 must preserve the product trust boundary: diagnostic leniency is allowed for routing, but not for falsely marking a candidate as merge-safe.
- **D-11:** A clearly incompatible result must still terminate the candidate decisively; only plausible recovery scenarios get the benefit of the doubt.

### the agent's Discretion
- Exact naming of new diagnosis categories and result enums
- Whether to enrich the existing diagnosis dict versus introducing a dedicated typed structure
- How much group-history evidence should influence recoverability versus remaining informational only

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition
- `.planning/ROADMAP.md` - defines the goal and success criteria for Phase 2
- `.planning/PROJECT.md` - defines the milestone goal, constraints, and trust boundary
- `.planning/REQUIREMENTS.md` - defines `SYNC-01`, `SYNC-02`, and `SYNC-03`
- `.planning/STATE.md` - records the current milestone position and blockers

### Existing phase context
- `.planning/phases/01-repo-hygiene-baseline/01-CONTEXT.md` - establishes prior project-level planning patterns and tracked-artifact conventions

### Sync diagnosis code
- `src/analyzer.py` - current sync diagnosis entrypoint, runtime heuristics, and final-file validation
- `src/audio_fingerprint.py` - current multi-position fingerprint measurement and classification behavior
- `src/trigger.py` - current orchestration, fallback routing, and diagnosis handling
- `src/sync_intelligence.py` - compatibility-history semantics and cut-mismatch penalties
- `src/notifier.py` - status taxonomy and operator-facing sync messages
- `src/config.py` - current sync, diagnostics, and fingerprint knobs

### Test coverage
- `tests/test_analyzer.py` - current sync diagnosis expectations
- `tests/test_trigger.py` - orchestration behavior around diagnosis, fingerprint, and fallback
- `tests/test_media_integration.py` - real-media fixture coverage for sync-ok and cut-mismatch cases
- `tests/test_sync_intelligence.py` - history handling for cut-mismatch outcomes

### Codebase guidance
- `.planning/codebase/ARCHITECTURE.md` - orchestration/data-flow overview
- `.planning/codebase/CONCERNS.md` - existing functional and architectural risks around sync and replacement
- `.planning/codebase/TESTING.md` - current testing strategy and relevant suites

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src.analyzer.diagnose_sync()` already returns a structured dict and is the natural place to expand recoverability semantics.
- `src.audio_fingerprint.fingerprint_sync()` already measures alignment at multiple positions (`head`, `mid`, `tail`) and can supply stronger evidence than plain duration deltas.
- `src.trigger._should_run_fingerprint()` already centralizes one routing decision for extra sync analysis.
- `src.sync_intelligence.GroupHistoryManager` already tracks prior outcomes that may help annotate risky groups or sources.

### Established Patterns
- Sync decisions are represented as categories plus supporting metadata carried in `context`.
- `src.trigger.py` currently treats diagnosis categories as both operator-facing statuses and orchestration control flow.
- Validation and replacement remain conservative and centralized in `src.merger.py` plus `src.analyzer.validate_final_file()`.
- Test coverage already favors mocked orchestration plus synthetic media fixtures, which is the right seam for this phase too.

### Integration Points
- `src/analyzer.py` is the primary integration point for richer recoverability classification.
- `src/trigger.py` must stop equating "large diff" with terminal fallback and instead branch on recoverability state.
- `src/notifier.py`, `history.json`, `group_history.json`, and queue metadata will need aligned vocabulary for new diagnosis outcomes.
- `tests/test_analyzer.py`, `tests/test_trigger.py`, and `tests/test_media_integration.py` are the main verification surface for this phase.

</code_context>

<specifics>
## Specific Ideas

- The motivating real-world failure mode is losing rare PT-BR candidates because the only mismatch is intro/outro or another non-structural runtime difference.
- The user explicitly wants the pipeline to keep those candidates alive long enough for later recovery rather than throwing them away on the first duration check.
- A "recoverable but not yet safe" middle state is essential; the current binary feel of sync-ok versus cut-mismatch is too blunt for this milestone.

</specifics>

<deferred>
## Deferred Ideas

- Implementing the actual automatic recovery mechanics with FFmpeg offset/cut operations - belongs to Phase 3
- Exposing operator-driven manual retry/force flows - belongs to Phase 4
- Broader refactors of `src/trigger.py` unrelated to sync recoverability - still deferred outside this milestone unless required tactically

</deferred>

---

*Phase: 02-recoverability-diagnostics*
*Context gathered: 2026-03-25*
