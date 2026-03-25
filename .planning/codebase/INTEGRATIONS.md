# Integrations

## Resumo

O projeto integra multiplos servicos locais e remotos para detectar filmes 4K importados, localizar um release 1080p com audio PT-BR e completar o mux com seguranca.

## Radarr

- Cliente principal em `src/radarr_client.py`
- Trigger de entrada descrito no `README.md` e consumido por `src/trigger.py`
- Endpoints relevantes:
  - `/api/v3/movie`
  - `/api/v3/release`
  - `/api/v3/tag`
  - `/api/v3/movie/editor`
  - `/api/v3/system/status` via `src/tools/preflight.py`
- Funcoes importantes:
  - `get_movie_by_tmdbid`
  - `get_movie_by_file_path`
  - `find_best_ptbr_release`
  - `rescan_movie`
  - `apply_success_tag`

## qBittorrent

- Cliente em `src/qbit_client.py`
- Autenticacao via `/api/v2/auth/login`
- Operacoes usadas:
  - listar torrents por tag e hash
  - adicionar torrent
  - retomar torrents pausados
  - ajustar prioridade
  - remover torrent ao final
- Convencoes de integracao:
  - categoria `ptbrmerger`
  - tag `ptbrmerger-tmdbid-<tmdbId>`

## FFmpeg / FFprobe

- Chamados via `subprocess` em `src/analyzer.py`, `src/merger.py` e `src/audio_fingerprint.py`
- Responsabilidades:
  - inspecao de streams e duracao
  - extracao da faixa PT-BR
  - mux do arquivo final
  - leitura de PCM para fingerprint

## Discord Webhook

- Integracao em `src/notifier.py`
- Fluxo de update progressivo por `send_progress_update` e `notify_status`
- A mensagem pode ser criada e depois editada ao longo do pipeline
- `src/tools/refresh_webhook.py` reconstrui ou atualiza mensagens a partir do estado atual

## Bazarr

- Cliente opcional em `src/bazarr_client.py`
- Usado como fallback informativo quando nao ha release util ou seeds disponiveis
- Endpoint consultado: `/api/movies`
- Resultado nao altera o mux diretamente; hoje serve como enriquecimento e diagnostico

## Sistema de Arquivos Local

- Leitura do filme 4K original via caminhos obtidos do Radarr
- Resolucao do arquivo 1080p baixado via `content_path` ou pasta do qBittorrent
- Escrita de artefatos temporarios ao lado do arquivo alvo:
  - `audio_ptbr.eac3`
  - `output_tmp.mkv`
  - `output_opt_tmp.mkv`

## Fixtures e Snapshots

- `scripts/capture_api_snapshots.py` captura payloads sanitizados
- `tests/test_data/api_snapshots/` armazena snapshots de Radarr, qBittorrent e Bazarr
- `scripts/generate_media_fixtures.py` e `tests/support/media_fixtures.py` suportam fixtures de midia sintetica

## Acoplamentos Relevantes

- `src/trigger.py` acopla quase todas as integracoes diretamente
- `src/tools/preflight.py` valida dependencias operacionais antes de rodar em ambiente real
- A configuracao central em `src/config.py` e singleton por processo, o que simplifica consumo mas aumenta acoplamento global
