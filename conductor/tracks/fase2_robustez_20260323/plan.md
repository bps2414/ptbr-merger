# Implementation Plan: Fase 2 - Robustez e Integridade

**Objetivo:** Implementar persistência de fila, validação pós-mux, retry com backoff e notificações ricas no Discord.

## Phase 1: Persistência de Estado (Queue Manager)
- [ ] Task: Criar `src/queue_manager.py` (TDD)
    - [ ] Escrever testes unitários para operações CRUD da fila em `queue.json`
    - [ ] Implementar `QueueManager` com controle de estados (PENDING, PROCESSING, ABANDONED)
- [ ] Task: Integração no `trigger.py`
    - [ ] Implementar loop de consumo da fila sequencial no entrypoint principal
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Persistência de Estado' (Protocol in workflow.md)

## Phase 2: Safety Net do Pós-Mux
- [ ] Task: Implementar Validador em `analyzer.py` (TDD)
    - [ ] Escrever testes unitários para verificar presença de áudio `por` e duração comparada
    - [ ] Implementar função `validate_final_file` usando `ffprobe`
- [ ] Task: Blindagem em `merger.py`
    - [ ] Integrar validador no fluxo de `replace_original` com política de "não deleção" em caso de erro
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Safety Net do Pós-Mux' (Protocol in workflow.md)

## Phase 3: Resiliência de Rede (API Backoff)
- [ ] Task: Criar Decorador `exponential_backoff` (TDD)
    - [ ] Escrever testes unitários simulando falhas de API (404, 500, timeouts)
    - [ ] Implementar decorador em `src/radarr_client.py` com backoff (1s, 2s, 4s, 8s)
- [ ] Task: Aplicar decorador em todos os métodos de rede do `radarr_client.py`
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Resiliência de Rede' (Protocol in workflow.md)

## Phase 4: Discord Rich Embeds & Dynamic Updates
- [ ] Task: Evoluir `notifier.py` para PATCH e Embeds
    - [ ] Implementar envio e edição de mensagens via PATCH no Webhook
    - [ ] Adicionar suporte a Embeds ricos (Thumbnail do Radarr, campos de status)
- [ ] Task: Integração de progresso dinâmico no `trigger.py`
    - [ ] Atualizar a mesma mensagem Discord durante as etapas do processo
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Discord Rich Embeds' (Protocol in workflow.md)
