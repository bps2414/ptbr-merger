# Spec: Fase 2 - Robustez, Integridade e Diagnóstico Operacional

**Visão Geral**
Esta track visa transformar o PTBRMerger de um MVP funcional em um sistema resiliente para produção. O foco deixa de ser apenas "não quebrar" e passa a incluir: validação forte antes de ações destrutivas, diagnóstico de incompatibilidades de runtime/sync, observabilidade estruturada e feedback operacional claro para o usuário e para o Radarr.

## Estado Atual Confirmado
- O fluxo de Bypass já possui detecção de duplicata no qBittorrent por `infohash`, reaplicação de `category/tag` e reaproveitamento de torrents já existentes.
- Quando o torrent duplicado já está concluído, o `trigger.py` já consegue acionar o processamento retroativo imediatamente, sem depender de um novo callback do qBittorrent.
- A validação de sincronia pré-mux e o fallback entre candidatos já existem; esta track não deve reimplementar essa lógica, apenas reforçar garantias ao redor dela.

## 1. Persistência Operacional Leve (Ledger/Lock)
- **Arquivo:** `src/queue_manager.py` (Novo, se necessário)
- **Persistência:** `queue.json` na raiz ou conforme config.
- **Campos mínimos:** `tmdbId`, `phase`, `attempts`, `status` (PENDING, PROCESSING, ABANDONED), `timestamp`.
- **Comportamento:** O sistema continua **dirigido por eventos** do Radarr/qBittorrent; ele não deve virar um worker contínuo. Se a persistência for implementada, ela deve servir para serializar operações críticas e registrar retomadas/idempotência entre eventos concorrentes, não para gerenciar o ciclo de download que já é persistido pelo qBittorrent.

## 2. Safety Net Pós-Mux
- **Local:** `src/merger.py` (Função `replace_original`).
- **Lógica:** Antes de `os.replace`, rodar `ffprobe` no arquivo temporário.
- **Validação:** 
    - Deve possuir stream `a:language=por`.
    - Duração deve bater com o original (tolerância 30s).
- **Fallback:** Se falhar, NÃO deletar o original, logar erro crítico e notificar.

## 3. Sync Robustness & Diagnostics
- **Runtime oficial:** Comparar a duração do 4K e do candidato 1080p com o runtime esperado do filme (TMDb/Radarr) para identificar corte especial, release incompleto ou versão incompatível antes do mux.
- **Proveniência do candidato:** Registrar de forma estruturada `release title`, `indexer`, `infohash`, `source`, duração do 4K, duração do 1080p, `diff` de sync e motivo do descarte/fallback.
- **Offset diagnóstico:** Introduzir estimativa de offset para diferenciar "offset simples" de "cut mismatch".
- **Auto-offset:** Só deve existir como caminho opcional e protegido por flag/config, aplicado apenas quando a heurística indicar alta confiança de offset uniforme e não corte diferente.

## 4. Decorador de Retry (Exponential Backoff)
- **Local:** `src/radarr_client.py` (Aplicar em métodos de rede).
- **Algoritmo:** Customizado (Zero dependências externas), 1s, 2s, 4s, 8s max.
- **Objetivo:** Curar falhas transitórias em chamadas à API do Radarr/Prowlarr.
- **Escopo de retry:** timeout, erro de conexão, `429` e `5xx`.
- **Fora de retry por padrão:** `400`, `401`, `403` e `404`, para não mascarar erro permanente/configuração incorreta.
- **Runtime do processo:** Registrar também tempo total e tempo por etapa para identificar gargalos operacionais reais (busca, download, extract, mux, replace).

## 5. Observabilidade & Discord Rich Feedback
- **Histórico estruturado:** Salvar eventos críticos em `history.json` com campos como `timestamp`, `tmdbId`, `status`, `release_escolhida`, `candidatos_tentados`, `runtime_4k`, `runtime_1080p`, `diff_sync`, `offset_estimado`, `duracao_processo`.
- **Decisão rastreável:** Completar o log de scoring e descarte para registrar também por que cada candidato foi rejeitado (blacklist, qualidade, corte, runtime, offset, sync).
- **Local:** `src/notifier.py`.
- **Funcionalidade:** Usar `wait=true` na criação da mensagem para obter `message_id` e editar a mesma mensagem via PATCH no endpoint de mensagem do webhook.
- **Embed:** Thumbnail via TMDb/Radarr, status detalhado, release escolhida, indexer, score, candidato atual, barra de progresso textual e duração total do processo.

## 6. External State Feedback
- **Radarr:** Após sucesso final, aplicar uma tag de estado operacional como `ptbr-merged` para evitar retrabalho e facilitar filtro/diagnóstico na UI.
- **Escopo:** Esta fase move apenas o feedback mínimo ao Radarr para dentro da robustez; integrações mais amplas como Jellyfin podem continuar fora desta track.

## Requisitos Não-Funcionais
- **TDD:** Cobertura de testes unitários para persistência operacional, decorador de retry, validador pós-mux e diagnósticos de sync/offset.
- **Clean Code:** Manter modularidade e responsabilidade única.

## Critérios de Aceite
- Se houver persistência operacional, ela deve impedir duplicidade/reentrância indevida entre eventos e permitir retomada segura de fases internas interrompidas.
- O arquivo original (4K) só pode ser deletado se o validador pós-mux passar.
- Candidatos rejeitados devem deixar rastro estruturado com motivo explícito.
- O sistema deve distinguir de forma observável entre `cut mismatch`, `offset simples` e falha genérica de sync.
- Falhas transitórias de rede no Radarr/Prowlarr não devem quebrar o fluxo (retry automático dentro do escopo definido).
- O histórico do processo deve registrar runtimes do filme e runtimes das etapas.
- Uma única mensagem no Discord deve ser atualizada até o final do processo.
- O Radarr deve refletir o estado de sucesso final via tag operacional mínima.
