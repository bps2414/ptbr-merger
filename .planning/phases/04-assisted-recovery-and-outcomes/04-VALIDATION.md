---
phase: 04
slug: assisted-recovery-and-outcomes
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-26
updated: 2026-03-26
---

# Phase 04 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none - existing project conventions |
| **Quick run command** | `pytest -q tests/test_trigger.py tests/test_notifier.py tests/test_tools.py` |
| **Full suite command** | `pytest -q tests/test_trigger.py tests/test_notifier.py tests/test_tools.py tests/test_sync_intelligence.py tests/test_media_integration.py` |
| **Compile command** | `python -m compileall src tests` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest -q tests/test_trigger.py tests/test_notifier.py tests/test_tools.py`
- **After every plan wave:** Run `pytest -q tests/test_trigger.py tests/test_notifier.py tests/test_tools.py tests/test_sync_intelligence.py`
- **Before `$gsd-verify-work`:** Run `pytest -q tests/test_trigger.py tests/test_notifier.py tests/test_tools.py tests/test_sync_intelligence.py tests/test_media_integration.py` and `python -m compileall src tests`
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | MAN-01 | orchestration | `pytest -q tests/test_trigger.py -k manual_recovery_cli` | yes | green |
| 04-01-02 | 01 | 1 | MAN-02 | orchestration | `pytest -q tests/test_trigger.py -k manual_recovery` | yes | green |
| 04-02-01 | 02 | 2 | OBS-01 | notifier/tooling | `pytest -q tests/test_notifier.py tests/test_tools.py -k manual` | yes | green |
| 04-02-02 | 02 | 2 | OBS-02 | history/scoring | `pytest -q tests/test_sync_intelligence.py tests/test_trigger.py -k manual` | yes | green |
| 04-03-01 | 03 | 3 | TEST-02 | orchestration | `pytest -q tests/test_trigger.py -k 'manual'` | yes | green |
| 04-03-02 | 03 | 3 | TEST-02 | integration + compile | `pytest -q tests/test_media_integration.py tests/test_trigger.py tests/test_notifier.py tests/test_tools.py tests/test_sync_intelligence.py` and `python -m compileall src tests` | yes | green |

---

## Wave 0 Requirements

Existing infrastructure already covers:

- CLI/orchestration regressions in `tests/test_trigger.py`
- notifier/embed assertions in `tests/test_notifier.py`
- operator tooling checks in `tests/test_tools.py`
- compatibility history semantics in `tests/test_sync_intelligence.py`
- fixture-backed media verification in `tests/test_media_integration.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Operator command examples in `README.md` are understandable for a real manual retry | MAN-01, MAN-02 | Unit tests can assert strings exist, but not whether the flow is understandable to a human operator under pressure | Read the documented manual recovery command examples and confirm the required inputs (`tmdb`, candidate, offset/trim, artifact retention) are obvious |
| Discord wording clearly distinguishes manual failure from structural incompatibility in a real channel | OBS-01, OBS-02 | Mock tests cover payload shape, not actual operator readability | Trigger a dry-run/manual terminal update and verify the embed text names manual pending/running/failed/success explicitly |

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies
- [x] Sampling continuity preserved
- [x] Wave 0 covers all required references
- [x] No watch-mode flags
- [x] Feedback latency < 120s
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Full phase suite passed on 2026-03-26
- [x] `python -m compileall src tests` passed on 2026-03-26

**Approval:** passed on 2026-03-26
