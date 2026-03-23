# Plan: Fase 2 - Robustez e Integridade

Esta track foi registrada formalmente no Conductor. O plano completo e a especificação podem ser encontrados em:
- [Especificação](./conductor/tracks/fase2_robustez_20260323/spec.md)
- [Plano Detalhado](./conductor/tracks/fase2_robustez_20260323/plan.md)

## Resumo das Atividades

### Phase 1: Persistência de Estado (Queue Manager)
- [ ] Task: Criar `src/queue_manager.py` (TDD)
    - [ ] Escrever testes unitários para operações CRUD da fila em `queue.json`
    - [ ] Implementar `QueueManager` com controle de estados (PENDING, PROCESSING, ABANDONED)
- [ ] Task: Integração no `trigger.py`
    - [ ] Implementar loop de consumo da fila sequencial no entrypoint principal

### Phase 2: Safety Net do Pós-Mux
- [ ] Task: Implementar Validador em `analyzer.py` (TDD)
- [ ] Task: Blindagem em `merger.py` (Não deleção em erro)

### Phase 3: Resiliência de Rede (API Backoff)
- [ ] Task: Criar Decorador `exponential_backoff` (TDD)
- [ ] Task: Aplicar decorador em `radarr_client.py`

### Phase 4: Discord Rich Embeds & Dynamic Updates
- [ ] Task: Evoluir `notifier.py` para PATCH e Embeds
- [ ] Task: Integração de progresso dinâmico no `trigger.py`

---

**Sugestão de Primeira Sub-Tarefa:**
- **Task:** Criar testes unitários para a manipulação da fila (`queue.json`) em `src/queue_manager.py`.
- **Objetivo:** Garantir que o estado do processo (tmdbId, status, timestamp) seja persistido e lido corretamente.
