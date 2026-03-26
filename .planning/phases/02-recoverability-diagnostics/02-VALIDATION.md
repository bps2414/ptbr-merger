---
phase: 02
slug: recoverability-diagnostics
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-25
---

# Phase 02 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none - existing project conventions |
| **Quick run command** | `pytest -q tests/test_analyzer.py tests/test_trigger.py` |
| **Full suite command** | `pytest -q tests/test_analyzer.py tests/test_trigger.py tests/test_media_integration.py tests/test_sync_intelligence.py && python -m compileall src tests` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest -q tests/test_analyzer.py tests/test_trigger.py`
- **After every plan wave:** Run `pytest -q tests/test_analyzer.py tests/test_trigger.py tests/test_media_integration.py tests/test_sync_intelligence.py && python -m compileall src tests`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SYNC-01 | unit | `pytest -q tests/test_analyzer.py` | ✅ | ⬜ pending |
| 02-01-02 | 01 | 1 | SYNC-02 | unit | `pytest -q tests/test_analyzer.py` | ✅ | ⬜ pending |
| 02-02-01 | 02 | 2 | SYNC-03 | orchestration | `pytest -q tests/test_trigger.py` | ✅ | ⬜ pending |
| 02-02-02 | 02 | 2 | SYNC-01 | orchestration | `pytest -q tests/test_trigger.py` | ✅ | ⬜ pending |
| 02-03-01 | 03 | 3 | SYNC-02 | integration | `pytest -q tests/test_media_integration.py tests/test_sync_intelligence.py` | ✅ | ⬜ pending |
| 02-03-02 | 03 | 3 | SYNC-03 | compile + regression | `python -m compileall src tests` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Discord/webhook wording remains useful with new recoverability categories | SYNC-02 | Unit tests can assert strings but not operator readability in the real channel context | Trigger a dry-run notification path and confirm the message clearly distinguishes recoverable versus terminal mismatch |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
