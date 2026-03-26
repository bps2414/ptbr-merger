---
status: complete
phase: 02-recoverability-diagnostics
source:
  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md
  - 02-03-SUMMARY.md
started: 2026-03-25T22:52:00Z
updated: 2026-03-25T23:12:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Preservar candidato recuperavel
expected: Quando um candidato PT-BR tem diferenca grande de runtime, mas o diagnostico indicar caso plausivelmente recuperavel (por exemplo, intro/outro diferente ou mismatch ambiguo), o pipeline nao deve descartar o candidato nem disparar fallback terminal imediatamente. O candidato deve permanecer preservado para recovery futuro, com status recuperavel visivel.
result: pass

### 2. Rejeitar mismatch terminal com seguranca
expected: Quando o diagnostico concluir que o candidato e estruturalmente incompatível, o pipeline deve encerrar esse candidato de forma explicita como terminal, permitindo fallback normal em vez de preserva-lo como se ainda fosse recuperavel.
result: pass

### 3. Expor taxonomia nova em status e historico
expected: Os status e o historico devem diferenciar claramente intro/outro diferente, mismatch ambiguo recuperavel e corte incompatível terminal, sem penalizar os casos recuperaveis como se fossem fracasso terminal.
result: pass

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[]
