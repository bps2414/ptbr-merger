# Phase 1: Repo Hygiene Baseline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 01-repo-hygiene-baseline
**Areas discussed:** Tracking policy, Cleanup scope, Local tooling artifacts, Documentation boundary

---

## Tracking policy

| Option | Description | Selected |
|--------|-------------|----------|
| A | Track code/docs only; local runtime, caches, and tooling stay unversioned | ✓ |
| B | Same base policy, but keep some local/dev artifact tracked | |
| C | Custom tracking policy | |

**User's choice:** A
**Notes:** `.planning/` remains tracked. Local config, runtime JSON, logs, caches, and local tooling artifacts are not versioned.

---

## Cleanup scope

| Option | Description | Selected |
|--------|-------------|----------|
| A | Conservative: only restore ignore rules going forward | |
| B | Complete with care: clean current noise safely without deleting important local data | ✓ |
| C | Complete and more aggressive | |

**User's choice:** B
**Notes:** Preserve `config.yml`. Keep runtime JSON files as local operator data instead of blindly deleting them.

---

## Local tooling artifacts

| Option | Description | Selected |
|--------|-------------|----------|
| A | Ignore all local tooling artifacts, no reorganization now | ✓ |
| B | Ignore all and propose moving some later | |
| C | Keep some visible/tracked | |

**User's choice:** A
**Notes:** `.codex/`, `.codex-repro-*`, `.runtime-archive/`, `tmp/`, and `get-shit-done-cc-1.28.0.tgz` are local-only for this phase.

---

## Documentation boundary

| Option | Description | Selected |
|--------|-------------|----------|
| A | Minimal: only fix ignore rules | |
| B | Pragmatic: add a short README section documenting tracked vs local files | ✓ |
| C | More formal: additional process docs | |

**User's choice:** B
**Notes:** Keep docs light. README gets the boundary; no extra bureaucracy.

---

## the agent's Discretion

- Final `.gitignore` pattern grouping and comments
- Exact README wording and section placement

## Deferred Ideas

- Reorganize local tooling directories later if workspace cleanliness becomes a separate concern
