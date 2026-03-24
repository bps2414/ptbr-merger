# Implementation Plan: Fase 2 - Robustez, Integridade e Diagnóstico Operacional

**Objetivo:** endurecer o PTBRMerger para operação real com validação forte antes de ações destrutivas, diagnóstico de incompatibilidades, persistência operacional leve, observabilidade estruturada e feedback externo confiável.

**Status atual:** implementado.

## Baseline que já existia antes da execução desta track
- Duplicata do qBittorrent detectada por `infohash`
- Reaplicação de `category/tag` em torrents já existentes
- Acionamento retroativo imediato quando o torrent duplicado já está concluído
- Fallback entre candidatos após falhas de sync/stream

## Phase 1: Persistência Operacional Leve
- [x] Confirmar que o projeto continua orientado a eventos e não vira worker contínuo
- [x] Criar `src/queue_manager.py`
- [x] Persistir estado em `queue.json`
- [x] Implementar estados `PENDING`, `PROCESSING`, `FAILED`, `ABANDONED`, `SUCCESS`
- [x] Integrar o ledger no `trigger.py` para anti-reentrância e abandono por tentativas
- [x] Cobrir ledger com testes unitários

**Entregue em código**
- `src/queue_manager.py`
- integração no `src/trigger.py`
- `tests/test_queue_manager.py`

## Phase 2: Safety Net do Pós-Mux
- [x] Implementar `validate_final_file` em `src/analyzer.py`
- [x] Confirmar faixa PT-BR e duração compatível antes do replace
- [x] Adicionar `validate_and_replace` em `src/merger.py`
- [x] Bloquear substituição destrutiva se a validação final falhar
- [x] Preservar artefatos temporários em caso de falha, conforme config
- [x] Mover cleanup destrutivo do qBittorrent para depois do sucesso real
- [x] Cobrir a blindagem com testes

**Entregue em código**
- `src/analyzer.py`
- `src/merger.py`
- `src/trigger.py`
- `tests/test_analyzer.py`
- `tests/test_merger.py`
- `tests/test_trigger.py`

## Phase 3: Sync Robustness & Diagnostics
- [x] Enriquecer análise com `runtime_4k`, `runtime_1080p` e `runtime_oficial`
- [x] Introduzir classificação `SYNC_OK`, `CUT_MISMATCH`, `OFFSET_SUSPECTED`, `RUNTIME_INCOMPATIBLE`, `UNKNOWN_SYNC_FAILURE`
- [x] Adicionar estimativa de offset como diagnóstico
- [x] Persistir release, indexer, infohash, sync diff e offset estimado
- [x] Registrar razão de fallback e falha no histórico
- [x] Cobrir o diagnóstico com testes

**Entregue em código**
- `src/analyzer.py`
- `src/trigger.py`
- `history.json` como trilha estruturada em runtime
- `tests/test_analyzer.py`
- `tests/test_trigger.py`

## Phase 4: Resiliência de Rede & Runtime de Processo
- [x] Implementar decorador `exponential_backoff` em `src/radarr_client.py`
- [x] Retentar apenas timeout, conexão, `429` e `5xx`
- [x] Garantir que `400/401/403/404` não entrem em retry padrão
- [x] Aplicar retry ao cliente Radarr crítico
- [x] Registrar runtime por etapa no `trigger.py`
- [x] Expor tempos por etapa em log e histórico
- [x] Cobrir retry com testes

**Entregue em código**
- `src/radarr_client.py`
- `src/trigger.py`
- `tests/test_radarr_client.py`

## Phase 5: Observabilidade & Discord Rich Feedback
- [x] Criar `src/history_manager.py`
- [x] Persistir eventos estruturados em `history.json`
- [x] Completar logging de decisões e fallback relevantes
- [x] Evoluir `src/notifier.py` para criação + edição da mesma mensagem via webhook
- [x] Adicionar embeds ricos com poster/backdrop, progresso, ETA, release e diagnóstico
- [x] Integrar progresso dinâmico no `trigger.py`
- [x] Cobrir notifier/history com testes

**Entregue em código**
- `src/history_manager.py`
- `src/notifier.py`
- `src/trigger.py`
- `tests/test_history_manager.py`
- `tests/test_notifier.py`

## Phase 6: External State Feedback
- [x] Aplicar tag `ptbr-merged` no Radarr após sucesso final
- [x] Manter operação idempotente via Movie Editor `applyTags=add`
- [x] Garantir que o sucesso final só seja emitido depois de `rescan` + tag
- [x] Validar o caminho com testes

**Entregue em código**
- `src/radarr_client.py`
- `src/trigger.py`
- `tests/test_radarr_client.py`
- `tests/test_trigger.py`

## Verificação executada
- [x] `pytest -q`
- [x] `python -m compileall src tests`
- [ ] `ruff check src tests` (bloqueado: `ruff` não instalado neste ambiente)

## Artefatos auxiliares entregues junto
- [x] `README.md` reescrito para refletir o estado real do projeto
- [x] `.gitignore` mínimo para `history.json`, `queue.json` e `*.pyc`
- [x] Repositório GitHub criado e push realizado

## Pendências pós-Phase 2
- [ ] Refinar ainda mais o logging de todos os candidatos rejeitados por score/ausência de URL
- [ ] Limpeza de arquivos rastreados de log/cache já existentes no repositório
- [ ] Avançar para os itens restantes da Fase 3/Fase 4 do roadmap principal
