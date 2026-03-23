# PTBRMerger — Roadmap v2

---

## Fase 1 — MVP (Em andamento ~90%)

### Concluído

- [x] Stack *arr completo no Windows — qBittorrent, Prowlarr, Radarr, Jellyfin, Jellyseerr, Bazarr, Configarr com Custom Formats PT-BR
- [x] 7 módulos Python implementados — `config`, `notifier`, `analyzer`, `merger`, `radarr_client`, `qbit_client`, `trigger`
- [x] Bypass qBittorrent direto — contorna limitação do Radarr de não permitir filme duplicado
- [x] Scoring multicamada PT-BR — 4 níveis (keywords, indexer BR, medium, qualidade). Release correta escolhida, BYNDR derrubado
- [x] Top 5 candidatos com fallback — tenta próximo automaticamente em `SYNC_MISMATCH` ou `NOT_FOUND_STREAM`
- [x] `validate_sync` + pré-filtro de corte — detecta releases de cortes diferentes antes do mux (threshold configurável)
- [x] Fluxo Modo 1 e Modo 2 validados em dry-run
- [x] qBittorrent injetando torrent e chamando trigger via `OnComplete`
- [x] Keywords PT-BR configuráveis em `config.yml` com high/medium/blacklist

### Pendente — bloqueador da Fase 1

- [x] **Teste real do ffmpeg** `[BLOQUEADOR]` — fluxo completo validado (extract + mux + replace_original) no filme Chainsaw Man: Reze Arc
- [x] Corrigir threshold de sync e fallback automático entre candidatos após `SYNC_MISMATCH`
- [ ] **Git inicializado** — controle de versão. Fazer ANTES de qualquer sessão de trabalho

---

## Fase 2 — Robustez e integridade

### Core — sem isso o sistema não é confiável em produção

- [ ] **Verificação pós-mux** `[core]` — ffprobe no arquivo final confirmando que a faixa PT-BR está presente e com `language=por` correto antes de deletar o 1080p. Se falhar → mantém o 1080p e loga erro
- [ ] **Fila persistente em JSON** `[core]` — salva estado em `queue.json` com tmdbId, candidato atual, tentativas já feitas e timestamp. Retoma de onde parou após crash ou reinício do Windows
- [ ] **Retry com exponential backoff** `[core]` — chamadas de API com retry automático: 1s, 2s, 4s, 8s. Máximo configurável. Especialmente importante pra `find_best_ptbr_release` que pode demorar 60s
- [ ] **Proteção contra loop infinito** `[core]` — se o mesmo filme falhar X vezes seguidas, marca como `ABANDONED` no `queue.json` e para de tentar. X configurável no `config.yml`

### Logging — diagnóstico completo

- [ ] **Log estruturado em JSON** `[logging]` — além do log legível em `.log`, salvar cada evento em `history.json` com campos estruturados: `timestamp`, `tmdb_id`, `titulo`, `status`, `release_escolhida`, `candidatos_tentados`, `duracao_processo`. Facilita análise futura
- [ ] **Log de performance** `[logging]` — logar tempo de cada etapa: busca de releases, download do 1080p, extract, mux, replace. Ajuda a identificar gargalos
- [ ] **Log de decisões do scoring** `[logging]` — já existe parcialmente. Completar para logar por que cada candidato foi rejeitado (blacklist? qualidade? sync?) em vez de só logar os aceitos

### Notificações Discord — embed rico

- [ ] **Embed completo de progresso** `[ux]` — substituir a mensagem simples atual por embed rico com:
  - Capa do filme buscada via API do TMDb (`https://image.tmdb.org/t/p/w300/{poster_path}`) como thumbnail
  - Título, ano e nota do TMDb
  - Release escolhida com indexer de origem
  - Tiebreaker score e keywords que ativaram
  - Candidato número X de Y tentados
  - Tamanho do arquivo de áudio extraído
  - Duração total do processo com ETA durante download
  - Barra de progresso textual: `█████████░ 90%`
  - Cor verde SUCCESS, laranja WARNING (sync mismatch tentando próximo), vermelho ERROR

- [ ] **Notificação de progresso em tempo real** `[ux]` — editar a mensagem Discord durante o processo (via PATCH no webhook) mostrando o estado atual: `Buscando releases... → Baixando 1080p (45%)... → Extraindo áudio... → Muxando...`

- [ ] **Notificação de NOT_FOUND com alternativa** `[ux]` — quando não achar PT-BR, embed informando que Bazarr foi acionado para legenda. Não deixar o usuário sem feedback

---

## Fase 3 — Inteligência e automação

### Seleção inteligente de releases

- [ ] **Histórico de sucesso por grupo** `[perf]` — `group_history.json` que registra taxa de sucesso por release group. `BYNDR: 0/3 sync ok`, `SF: 2/2 sync ok`. Com o tempo o scoring considera isso como Nível 3.5 entre indexer BR e keywords medium
- [ ] **Aprendizado de sync por source** `[perf]` — registrar qual combinação de sources (4K source + 1080p source) costuma ter sync ok. Ex: `MA.WEB-DL 4K + AMZN.WEB-DL 1080p` → historicamente compatível
- [ ] **Retry agendado** `[perf]` — `NOT_FOUND` definitivo agenda retry automático em 3 e 7 dias no `queue.json`. Novos releases BR costumam aparecer dias depois do lançamento
- [ ] **Detecção de corte por duração do 4K** `[perf]` — comparar duração do 4K com a duração esperada do corte padrão (buscada no TMDb via `runtime`). Se o 4K for muito diferente do runtime oficial, é um corte especial — filtrar candidatos com mais agressividade

### Processamento em lote

- [ ] **Modo batch / scan-library** `[core]` — `python trigger.py --scan-library` varre toda a biblioteca do Radarr via `GET /api/v3/movie`, identifica filmes sem faixa PT-BR usando ffprobe e coloca na fila. Processa um por vez com intervalo configurável entre cada filme
- [ ] **Watchdog periódico** `[core]` — processo que roda a cada 24h verificando novos filmes importados que não passaram pelo PTBRMerger (por qualquer motivo) e os coloca na fila automaticamente
- [ ] **Prioridade na fila** `[ux]` — filmes adicionados recentemente têm prioridade sobre filmes antigos na fila. Filmes marcados como favoritos no Radarr têm prioridade máxima

### Qualidade do mux

- [ ] **Offset automático de áudio** `[perf]` — calcular o offset exato via Cross-Correlation (alass/scipy) e passar pro ffmpeg com `-itsoffset {offset}`. A única forma matemática cega de corrigir intro diferente ou créditos sem quebrar o sync inicial.
- [x] **Preservar chapter markers** `[perf]` — adicionado `-map_chapters 0` no comando de mux para preservar os capítulos do 4K original.
- [ ] **Normalização de volume** `[perf]` — aplicar `loudnorm` do ffmpeg pra equalizar volumes (Atenção: exige transcode do áudio EAC3, gerando consumo extra de CPU e mínima perda qualitativa vs `-c copy`).

### Integrações

- [ ] **Bazarr fallback inteligente** `[integração]` — `NOT_FOUND` definitivo chama `POST /api/subtitles` do Bazarr passando o path do filme. Força busca imediata de legenda PT-BR sem esperar o scan automático do Bazarr
- [ ] **Integração Jellyfin** `[integração]` — após mux bem-sucedido, chama `POST /Items/{id}/Refresh` da API do Jellyfin. A nova faixa PT-BR aparece imediatamente na interface sem esperar o scan noturno
- [ ] **Webhook Radarr de resposta** `[integração]` — adicionar tag `ptbr-merged` ao filme no Radarr após mux bem-sucedido. Permite filtrar na UI quais filmes já foram processados

---

## Fase 4 — Polish e comunidade

### Dashboard web

- [ ] **Dashboard web local** `[ux]` — página HTML servida em `localhost:5056` via Flask/FastAPI com:
  - Lista de filmes processados com poster, título, status e data
  - Fila ativa com ETA estimado
  - Histórico de candidatos tentados por filme (expandível)
  - Estatísticas: total processado, taxa de sucesso, indexers mais usados, grupos mais confiáveis
  - Botão "Reprocessar" por filme
  - Dark mode nativo

- [ ] **API REST do dashboard** `[ux]` — endpoints simples para integração futura:
  - `GET /api/status` — status geral
  - `GET /api/queue` — fila atual
  - `GET /api/history` — histórico
  - `POST /api/process/{tmdb_id}` — força processamento manual

### Otimizações técnicas

- [ ] **Fingerprint de áudio** `[perf]` — baixa só os primeiros 50MB do torrent via HTTP range request (quando `downloadUrl` for HTTP direto, não magnet) e roda ffprobe nesse trecho. Confirma PT-BR antes de baixar o arquivo completo. Economiza até 2GB por candidato descartado
- [ ] **Cache de resultados de busca** `[perf]` — se o mesmo filme foi buscado há menos de 6h e não achou, não busca de novo. Evita sobrecarregar os indexers com buscas repetidas do mesmo filme
- [ ] **Compressão de logs** `[perf]` — loguru já tem `rotation="10MB"` mas adicionar `compression="gz"` pra logs antigos. Evita acúmulo de logs grandes

### Publicação e comunidade

- [ ] **Setup automático via API** `[ux]` — `python setup.py` que:
  - Cria perfil `PTBRMerger` no Radarr via API
  - Cria tags `ptbrmerger` e `internacional`
  - Cria pasta `D:\data\temp\ptbrmerger`
  - Adiciona Root Folder no Radarr
  - Verifica ffmpeg e Python no PATH
  - Gera `config.yml` preenchido interativamente

- [ ] **Publicar no GitHub** — com:
  - README em PT-BR completo com screenshots
  - README em EN para alcance internacional
  - Releases versionadas com changelog
  - Issues templates para bug report e feature request
  - GitHub Actions para testes automáticos em cada PR
  - Wiki com guia de troubleshooting dos erros mais comuns

- [ ] **Integração com trash-guides-ptbr** `[integração]` — contribuir o projeto de volta pro repositório do marcosviniciusi como ferramenta complementar aos Custom Formats

---

## Status atual

```
Fase 1 ██████████████████  ~98%
Fase 2 ░░░░░░░░░░░░░░░░░░   0%
Fase 3 ░░░░░░░░░░░░░░░░░░   0%
Fase 4 ░░░░░░░░░░░░░░░░░░   0%
```

### Próxima ação imediata
```
git init && git add . && git commit -m "Fase 1 MVP"
```

---

## Legenda de tags

| Tag | Significado |
|---|---|
| `[core]` | Funcionalidade essencial — sem isso o sistema não é confiável |
| `[perf]` | Melhoria de performance ou inteligência |
| `[ux]` | Melhoria de experiência do usuário |
| `[logging]` | Diagnóstico e observabilidade |
| `[integração]` | Conexão com outros serviços do stack |
