---
phase: 03
slug: automatic-sync-recovery
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-26
---

# Phase 03 - Validation Strategy

> Per-phase validation contract for conservative automatic recovery.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Quick run command** | `pytest -q tests/test_trigger.py tests/test_merger.py` |
| **Recovery regression command** | `pytest -q tests/test_media_integration.py tests/test_analyzer.py` |
| **Full suite command** | `pytest -q tests/test_trigger.py tests/test_merger.py tests/test_media_integration.py tests/test_analyzer.py tests/test_sync_intelligence.py && python -m compileall src tests` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest -q tests/test_trigger.py tests/test_merger.py`
- **After every plan wave:** Run `pytest -q tests/test_media_integration.py tests/test_analyzer.py`
- **Before phase close:** Run full suite command
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 03-01-01 | 01 | 1 | AUTO-01 | unit/orchestration | `pytest -q tests/test_trigger.py tests/test_merger.py` | pending |
| 03-01-02 | 01 | 1 | AUTO-03 | unit/orchestration | `pytest -q tests/test_trigger.py tests/test_merger.py` | pending |
| 03-02-01 | 02 | 2 | AUTO-02 | orchestration | `pytest -q tests/test_trigger.py tests/test_analyzer.py` | pending |
| 03-02-02 | 02 | 2 | SAFE-01 | orchestration | `pytest -q tests/test_trigger.py tests/test_analyzer.py` | pending |
| 03-03-01 | 03 | 3 | TEST-01 | integration | `pytest -q tests/test_media_integration.py tests/test_analyzer.py` | pending |
| 03-03-02 | 03 | 3 | SAFE-01 | compile + regression | `python -m compileall src tests` | pending |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Recovery attempt logs remain understandable during a real candidate run | AUTO-03 | Automated tests can assert data, not operator readability under live flow | Replay a preserved candidate and confirm logs/history state show strategy attempted, evidence used, and failure/success reason clearly |

---

## Validation Sign-Off

- [x] All tasks have automated verification
- [x] Sampling continuity preserved
- [x] Full suite includes compile gate
- [x] `nyquist_compliant: true` set

**Approval:** pending
