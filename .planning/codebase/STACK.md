# Stack

## Resumo

`PTBRMerger` e um projeto Python orientado a automacao local para orquestrar Radarr, qBittorrent, FFmpeg/FFprobe e notificacoes Discord em um pipeline de mux de audio PT-BR.

## Linguagem e Runtime

- Linguagem principal: `Python 3.11+`
- Execucao principal via script: `src/trigger.py`
- Atalho Windows para execucao manual: `run.bat`
- Ambiente esperado: Windows, embora boa parte do codigo seja portavel via `pathlib`

## Dependencias Python

Dependencias declaradas em `requirements.txt`:

- `requests>=2.31.0` para HTTP com Radarr, qBittorrent, Bazarr e Discord
- `PyYAML>=6.0` para leitura de `config.yml`
- `loguru>=0.7.0` para logging estruturado em `src/notifier.py`
- `numpy>=1.26.0` para correlacao de fingerprint em `src/audio_fingerprint.py`

## Ferramentas Externas

- `ffmpeg` e `ffprobe` sao obrigatorios e configurados em `config.yml` ou `config.example.yml`
- `pytest` e usado pela suite em `tests/`
- Scripts batch em `scripts/` encapsulam comandos operacionais como `watch-log.bat` e `status.bat`

## Configuracao

- Config loader tipado em `src/config.py`
- Arquivo preferencial local: `config.yml`
- Template rastreado: `config.example.yml`
- Override por variaveis de ambiente:
  - `RADARR_URL`
  - `RADARR_API_KEY`
  - `QBITTORRENT_URL`
  - `QBITTORRENT_USERNAME`
  - `QBITTORRENT_PASSWORD`
  - `DISCORD_WEBHOOK_URL`

## Estrutura de Modulos Principais

- `src/trigger.py`: orquestracao principal e CLI
- `src/radarr_client.py`: busca e ranking de releases
- `src/qbit_client.py`: injecao, deduplicacao e prioridade de torrents
- `src/analyzer.py`: `ffprobe`, deteccao PT-BR e diagnostico de sync
- `src/merger.py`: extracao, mux, validacao e replace
- `src/audio_fingerprint.py`: correlacao de offset via amostras PCM
- `src/notifier.py`: logger e mensagens Discord

## Estado e Artefatos de Runtime

Arquivos persistidos na raiz do repositorio:

- `queue.json`
- `retry_queue.json`
- `history.json`
- `group_history.json`
- `ptbrmerger.log`

## Sinais de Maturidade Tecnica

- Tipagem parcial com dataclasses em `src/config.py` e `src/qbit_client.py`
- Testes automatizados em `tests/`
- Ferramentas de operacao em `src/tools/`
- Cache de `__pycache__` e arquivos de runtime aparecem no workspace, o que indica repositorio usado tambem como ambiente operacional
