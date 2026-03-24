# Spec: Fase 2 - Robustez, Integridade e Diagnóstico Operacional

## Visão Geral
Esta track foi concluída para transformar o PTBRMerger de um MVP funcional em um pipeline bem mais seguro para produção. O foco entregue foi:

- validação forte antes de ações destrutivas
- diagnóstico observável de runtime/sync/offset
- persistência operacional leve entre eventos
- observabilidade estruturada
- feedback operacional claro no Discord e no Radarr

## Estado Atual Confirmado
- O fluxo de bypass já detecta duplicata por `infohash`, reaplica `category/tag` e reaproveita torrents já existentes no qBittorrent.
- Quando o torrent duplicado já está concluído, o `trigger.py` aciona o processamento retroativo imediatamente.
- O pipeline agora mantém estado operacional em `queue.json` e trilha histórica em `history.json`.
- O arquivo 4K original só é substituído após validação final positiva do MKV resultante.
- O sucesso final é refletido no Radarr com a tag `ptbr-merged`.
- A mesma mensagem do Discord é criada e atualizada via webhook com embed rico e progresso.

## 1. Persistência Operacional Leve
- **Implementado em:** `src/queue_manager.py`
- **Persistência:** `queue.json`
- **Campos atuais:** `tmdbId`, `phase`, `candidate_index`, `attempts`, `status`, `last_error`, `updated_at`
- **Estados atuais:** `PENDING`, `PROCESSING`, `FAILED`, `ABANDONED`, `SUCCESS`
- **Comportamento:** o projeto continua dirigido por eventos Radarr/qBittorrent; o ledger atua como trava/idempotência e não como worker contínuo.

## 2. Safety Net Pós-Mux
- **Implementado em:** `src/analyzer.py` e `src/merger.py`
- **Lógica:** `validate_final_file()` roda antes do replace destrutivo.
- **Validação atual:**
  - presença de stream PT-BR
  - duração compatível com o original
  - recusa explícita com motivo estruturado
- **Fallback atual:** se falhar, o original não é substituído, o qBittorrent não é limpo e a falha fica registrada.

## 3. Sync Robustness & Diagnostics
- **Implementado em:** `src/analyzer.py` e `src/trigger.py`
- **Classificações atuais:**
  - `SYNC_OK`
  - `CUT_MISMATCH`
  - `OFFSET_SUSPECTED`
  - `RUNTIME_INCOMPATIBLE`
  - `UNKNOWN_SYNC_FAILURE`
- **Dados atuais registrados:** `release_title`, `indexer`, `infohash`, `runtime_4k`, `runtime_1080p`, `runtime_oficial`, `diff`, `offset_estimate`
- **Auto-offset:** continua fora do caminho de sucesso padrão; apenas o diagnóstico foi entregue nesta fase.

## 4. Resiliência de Rede & Runtime de Processo
- **Implementado em:** `src/radarr_client.py`
- **Retry atual:** timeout, conexão, `429`, `5xx`
- **Sem retry padrão:** `400`, `401`, `403`, `404`
- **Runtime operacional:** o `trigger.py` mede e registra tempos por etapa como `resolve`, `sync`, `extract`, `mux`, `validate_replace`, `rescan_tag`, `cleanup`.

## 5. Observabilidade & Discord Rich Feedback
- **Histórico estruturado:** `history.json`
- **Manager dedicado:** `src/history_manager.py`
- **Notifier atual:** `src/notifier.py`
- **Capacidades atuais do embed:**
  - criação com `wait=true`
  - edição da mesma mensagem via PATCH
  - poster e backdrop quando presentes
  - título, fase, progresso, ETA, tempo decorrido
  - release, indexer, candidato, score
  - resumo de diagnóstico

## 6. External State Feedback
- **Implementado em:** `src/radarr_client.py`
- **Feedback atual:** tag `ptbr-merged`
- **Política atual:** operação idempotente via Movie Editor com `applyTags=add`

## Critérios de Aceite Atendidos
- [x] Persistência operacional impede reentrância indevida e suporta abandono seguro
- [x] O arquivo original só é trocado após validação final aprovada
- [x] Falhas e fallbacks deixam rastro estruturado
- [x] O sistema distingue `cut mismatch`, `offset suspeito` e incompatibilidade de runtime
- [x] Falhas transitórias de rede no Radarr não quebram o fluxo imediatamente
- [x] O histórico registra runtimes do filme e runtimes de etapas
- [x] Uma única mensagem no Discord pode ser atualizada até o final
- [x] O Radarr reflete o sucesso via tag operacional mínima

## Verificação
- `pytest -q` verde
- `python -m compileall src tests` verde
- `ruff check src tests` ainda pendente por ausência do binário neste ambiente
