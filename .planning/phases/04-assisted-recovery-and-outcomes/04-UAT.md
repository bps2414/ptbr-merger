---
status: complete
phase: 04-assisted-recovery-and-outcomes
source:
  - 04-01-SUMMARY.md
  - 04-02-SUMMARY.md
  - 04-03-SUMMARY.md
started: 2026-03-26T18:09:23.7231231-03:00
updated: 2026-03-26T18:13:41.0000000-03:00
---

## Current Test

[testing complete]

## Tests

### 1. Manual Recovery CLI Contract
expected: Ao executar um comando manual como `python src/trigger.py --manual-recovery --tmdb-id <tmdb> --qbit-path "<caminho>"` o fluxo aceita a tentativa sem exigir edição de código. Se faltar `--tmdb-id` ou `--qbit-path`, ele falha cedo com erro explícito de uso em vez de seguir com um estado ambíguo.
result: pass

### 2. Manual Lifecycle Messaging
expected: Durante ou após uma tentativa manual, as superfícies operacionais usam estados explícitos como `MANUAL_RECOVERY_PENDING`, `MANUAL_RECOVERY_RUNNING`, `MANUAL_RECOVERY_FAILED` ou `MANUAL_RECOVERY_SUCCESS`, sem confundir falha manual com incompatibilidade estrutural ou auto recovery.
result: pass

### 3. Status Snapshot Shows Replayable Metadata
expected: Ao rodar `python -m src.tools.status`, a seção `Manual Recoveries` mostra os metadados reaproveitáveis da tentativa manual, incluindo `manual_request_id`, candidato/offset/trim e o caminho da fonte quando existirem.
result: pass

### 4. Refresh Rebuilds Manual Terminal State
expected: Ao rodar `python -m src.tools.refresh_webhook --tmdb <tmdb>`, o comando consegue reconstruir um estado terminal manual a partir do histórico persistido e preservar o contexto manual no payload/notificação.
result: pass

### 5. Manual Flow Stays Conservative
expected: Quando a receita manual é válida, ela pode concluir com sucesso; quando o candidato é estruturalmente incompatível, o fluxo continua rejeitando com segurança e não trata isso como sucesso nem substitui o 4K por um resultado inválido.
result: pass

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
