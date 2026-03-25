# Conventions

## Estilo Geral

O codigo segue um Python pragmatico, mais orientado a fluxo operacional do que a refinamento academico. A base usa funcoes, dataclasses simples e bastante logging contextual.

## Convencoes de Codigo

- Funcoes e modulos em `snake_case`
- Constantes de modulo em caixa alta, como `_RETRYABLE_STATUS_CODES` em `src/radarr_client.py`
- Dataclasses para estruturas pequenas:
  - `AppConfig` em `src/config.py`
  - `QbitAddResult` em `src/qbit_client.py`
  - `QueueManager` e `RetryQueueManager`
- Uso frequente de `Path` em vez de concatenacao manual de strings

## Convencoes de Configuracao

- Config declarativa em YAML via `config.yml`
- Override de secrets/config por variaveis de ambiente em `src/config.py`
- `config.example.yml` funciona como contrato minimo do ambiente

## Convencoes de Logging e Diagnostico

- Logging centralizado em `src/notifier.py` com `loguru`
- Helpers `info`, `warning`, `error`, `debug` sao importados diretamente pelos modulos
- Status do pipeline usa codigos semanticos como:
  - `SUCCESS`
  - `NOT_FOUND`
  - `NO_AVAILABLE_SEEDS`
  - `OFFSET_SUSPECTED_FAILED`
  - `FINGERPRINT_LOW_CONFIDENCE`

## Convencoes de Fluxo

- O `trigger` tenta ser resiliente: registra historico, agenda retry e em muitos casos evita abortar o processo cedo demais
- Managers JSON criam arquivos vazios automaticamente se nao existirem
- Falhas recuperaveis tendem a ser persistidas antes de qualquer novo fallback

## Convencoes de Integracao

- qBittorrent usa categoria fixa `ptbrmerger`
- Tags seguem formato `ptbrmerger-tmdbid-<tmdbId>`
- Radarr usa tag de sucesso configuravel, default `ptbr-merged`

## Convencoes de Teste

- Testes usam bastante `unittest.mock.patch`
- `tmp_path` e empregado para isolar filesystem em `tests/test_tools.py` e `tests/test_trigger.py`
- Casos cobrem HTTP, heuristicas de release, ferramentas e fluxo principal

## Inconsistencias Notaveis

- Mistura de ingles e portugues em nomes, comentarios e mensagens
- Alguns textos no codigo aparecem com problemas de encoding em outputs lidos no terminal
- `src/trigger.py` concentra responsabilidade demais, fugindo do resto da modularizacao

## Indicacoes Praticas

- Ao alterar comportamento do pipeline, revisar sempre `src/trigger.py`, `src/radarr_client.py` e `tests/test_trigger.py`
- Ao mexer em schema/config, ajustar `src/config.py`, `config.example.yml` e `tests/test_config.py`
- Ao mexer em UX operacional, validar `src/notifier.py` e `tests/test_notifier.py`
