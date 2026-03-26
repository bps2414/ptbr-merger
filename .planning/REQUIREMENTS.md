# Requirements: PTBRMerger v0.4.5 Guided Operations

**Defined:** 2026-03-26
**Core Value:** When a 4K movie lacks PT-BR audio, the pipeline must recover a compatible PT-BR source and merge it safely without corrupting or wrongly replacing the original file.

## Current Status

Active milestone: `v0.4.5 Guided Operations`

Goal: make the existing local pipeline operable by a non-technical user through guided commands, doctor checks, and safer manual flows without introducing a heavy dashboard rewrite.

## v0.4.5 Requirements

### Guided Operations

- [ ] **OPS-01**: User can open a single guided command entrypoint and discover the main operational actions without memorizing CLI flags.
- [ ] **OPS-02**: User can choose common actions such as status, doctor, manual recovery, webhook refresh, and safe cleanup from a guided local menu.
- [ ] **OPS-03**: User sees clear next-step prompts after each guided operation instead of being dropped back into a blank terminal.

### Doctor and Diagnostics

- [ ] **DOC-01**: User can run one doctor/preflight command that checks local dependencies, config presence, and key integration reachability before a risky operation.
- [ ] **DOC-02**: User receives plain-language explanations for detected local problems and concrete fix suggestions.
- [ ] **DOC-03**: User can distinguish blocking problems from warnings so they know what must be fixed first.

### Guided Manual Recovery

- [ ] **REC-UX-01**: User can start manual recovery through a guided flow that asks for the required inputs instead of requiring raw trigger flags.
- [ ] **REC-UX-02**: User is prevented from launching an invalid manual recovery combination through inline validation and prompts.
- [ ] **REC-UX-03**: User can review the chosen manual recovery recipe before execution begins.

### Safe Operations and Documentation

- [ ] **SAFE-OPS-01**: User must explicitly confirm destructive or state-mutating maintenance actions in the guided flow.
- [ ] **SAFE-OPS-02**: User can see when an operation is dry-run, safe-read-only, or mutating before it starts.
- [ ] **GUIDE-01**: User has operator-facing docs/scripts in Portuguese that match the guided workflow instead of only raw developer commands.

## Future Requirements

- **UI-01**: Provide a lightweight local dashboard if the guided CLI proves insufficient for real operators.
- **ORCH-01**: Split orchestration responsibilities currently concentrated in `src/trigger.py`.
- **RANK-01**: Extract Radarr candidate ranking and fallback rules into dedicated modules.
- **QUAL-01**: Define a single validation entrypoint for test and compile checks.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full web dashboard | Too much surface area right now; guided local operations are a safer first step |
| Multi-user remote access | Current operating model is local and single-operator |
| Replacing JSON runtime persistence | Important later, but not required to make operations guided and safer now |
| Deep orchestration rewrite | Refactoring remains limited to what is necessary to support safe guided flows |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OPS-01 | Phase 6 | Pending |
| OPS-02 | Phase 6 | Pending |
| OPS-03 | Phase 6 | Pending |
| DOC-01 | Phase 7 | Pending |
| DOC-02 | Phase 7 | Pending |
| DOC-03 | Phase 7 | Pending |
| REC-UX-01 | Phase 8 | Pending |
| REC-UX-02 | Phase 8 | Pending |
| REC-UX-03 | Phase 8 | Pending |
| SAFE-OPS-01 | Phase 7 | Pending |
| SAFE-OPS-02 | Phase 8 | Pending |
| GUIDE-01 | Phase 9 | Pending |

**Coverage:**
- v0.4.5 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-26*
*Last updated: 2026-03-26 after initial definition*
