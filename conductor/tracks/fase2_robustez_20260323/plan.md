# Implementation Plan: Fase 2 - Robustez, Integridade e Diagnóstico Operacional

**Objetivo:** Endurecer o PTBRMerger com persistência operacional leve, validação pós-mux, diagnósticos de runtime/sync/offset, retry para falhas transitórias, observabilidade estruturada e feedback operacional ao usuário e ao Radarr.

**Baseline já implementado e fora do escopo desta track:**
- Detecção de duplicata do qBittorrent por `infohash`
- Reaplicação de `category/tag` em torrents já existentes
- Acionamento retroativo imediato quando o torrent duplicado já está concluído
- Validação de sincronia pré-mux com fallback entre candidatos

## Phase 1: Persistência Operacional Leve (Ledger/Lock)
- [ ] Task: Revalidar necessidade de `src/queue_manager.py` contra a arquitetura orientada a eventos
    - [ ] Confirmar se um `ledger`/`lock` é suficiente antes de introduzir fila persistida
    - [ ] Documentar claramente que o `trigger.py` não deve virar worker contínuo
- [ ] Task: Se confirmado necessário, criar `src/queue_manager.py` (TDD)
    - [ ] Escrever testes unitários para operações CRUD do `queue.json`
    - [ ] Implementar controle de estados (PENDING, PROCESSING, ABANDONED) para fases internas do pipeline
- [ ] Task: Integração no `trigger.py`
    - [ ] Aplicar serialização/idempotência apenas em seções críticas entre eventos concorrentes
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Persistência Operacional Leve' (Protocol in workflow.md)

## Phase 2: Safety Net do Pós-Mux
- [ ] Task: Implementar Validador em `analyzer.py` (TDD)
    - [ ] Escrever testes unitários para verificar presença de áudio `por` e duração comparada
    - [ ] Implementar função `validate_final_file` usando `ffprobe`
- [ ] Task: Blindagem em `merger.py`
    - [ ] Integrar validador no fluxo de `replace_original` com política de "não deleção" em caso de erro
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Safety Net do Pós-Mux' (Protocol in workflow.md)

## Phase 3: Sync Robustness & Diagnostics
- [ ] Task: Adicionar heurística de runtime/corte no `analyzer.py` (TDD)
    - [ ] Comparar runtime 4K e 1080p com runtime oficial do filme
    - [ ] Classificar suspeita de corte especial antes do mux
- [ ] Task: Introduzir diagnóstico de offset
    - [ ] Registrar `diff` e estimativa de offset por candidato
    - [ ] Diferenciar `offset simples` de `cut mismatch`
    - [ ] Se implementado, manter auto-offset atrás de flag/config e com critério conservador
- [ ] Task: Persistir proveniência e motivo do fallback
    - [ ] Registrar release, indexer, infohash, source e razão do descarte
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Sync Robustness & Diagnostics' (Protocol in workflow.md)

## Phase 4: Resiliência de Rede & Runtime de Processo
- [ ] Task: Criar Decorador `exponential_backoff` (TDD)
    - [ ] Escrever testes unitários simulando falhas transitórias de API (`429`, `5xx`, timeouts, conexão)
    - [ ] Escrever testes garantindo que `400/401/403/404` não entram em retry por padrão
    - [ ] Implementar decorador em `src/radarr_client.py` com backoff (1s, 2s, 4s, 8s)
- [ ] Task: Aplicar decorador em todos os métodos de rede do `radarr_client.py`
- [ ] Task: Registrar runtime operacional por etapa
    - [ ] Medir busca, download, extract, mux e replace
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Resiliência de Rede & Runtime de Processo' (Protocol in workflow.md)

## Phase 5: Observabilidade & Discord Rich Feedback
- [ ] Task: Implementar histórico estruturado
    - [ ] Criar `history.json` com eventos-chave do pipeline
    - [ ] Persistir runtime do filme, runtime das etapas, candidato escolhido e motivos de fallback
- [ ] Task: Completar logging de decisões
    - [ ] Logar candidatos rejeitados e o motivo explícito de rejeição
- [ ] Task: Evoluir `notifier.py` para PATCH e Embeds
    - [ ] Implementar criação com `wait=true` para capturar `message_id`
    - [ ] Implementar edição da mesma mensagem via PATCH no endpoint do webhook
    - [ ] Adicionar suporte a Embeds ricos (Thumbnail do Radarr, campos de status)
- [ ] Task: Integração de progresso dinâmico no `trigger.py`
    - [ ] Atualizar a mesma mensagem Discord durante as etapas do processo
- [ ] Task: Conductor - User Manual Verification 'Phase 5: Observabilidade & Discord Rich Feedback' (Protocol in workflow.md)

## Phase 6: External State Feedback
- [ ] Task: Integrar feedback mínimo ao Radarr
    - [ ] Aplicar tag `ptbr-merged` após sucesso final
    - [ ] Garantir que a tag não quebre idempotência nem reprocessamento controlado
- [ ] Task: Conductor - User Manual Verification 'Phase 6: External State Feedback' (Protocol in workflow.md)
