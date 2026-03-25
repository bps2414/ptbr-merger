# Structure

## Visao Geral

O repositorio mistura codigo de produto, ferramentas operacionais, dados de runtime, testes e artefatos do ecossistema Codex/GSD.

## Diretorios Principais

- `src/`: codigo principal da aplicacao
- `src/tools/`: CLIs auxiliares para status, preflight, refresh de webhook, higiene de runtime e leitura de log
- `tests/`: suite automatizada e suportes
- `tests/support/`: helpers de teste e geradores de fixtures
- `tests/test_data/`: snapshots de API e manifestos de fixtures
- `scripts/`: wrappers e utilitarios manuais, principalmente `.bat` e scripts de captura/fixtures
- `.codex/`: configuracao local do agente
- `.codex-gsd-localtest/`: artefatos de teste/local do ecossistema GSD

## Arquivos de Entrada e Configuracao

- `README.md`: documentacao operacional extensa
- `requirements.txt`: dependencias Python
- `config.example.yml`: template versionado
- `config.yml`: configuracao local ativa presente no workspace
- `run.bat`: launcher local para `src/trigger.py`

## Codigo Principal em `src/`

- `src/trigger.py`: maior modulo e ponto de orquestracao
- `src/radarr_client.py`: segundo maior modulo, com bastante regra de ranking
- `src/qbit_client.py`: integracao qBittorrent e deduplicacao
- `src/notifier.py`: logger e renderizacao de status
- `src/analyzer.py`, `src/merger.py`, `src/audio_fingerprint.py`: pipeline de midia
- `src/config.py`: schema de configuracao
- `src/*_manager.py` e `src/sync_intelligence.py`: persistencia e scoring historico

## Testes

Arquivos de teste importantes:

- `tests/test_trigger.py`
- `tests/test_radarr_client.py`
- `tests/test_qbit_client.py`
- `tests/test_analyzer.py`
- `tests/test_merger.py`
- `tests/test_tools.py`
- `tests/test_media_integration.py`
- `tests/test_api_snapshots.py`

## Convencoes de Nome

- Modulos Python em `snake_case`
- Testes seguem `test_<modulo>.py`
- Ferramentas CLI vivem sob `src/tools/`
- Estado operacional fica em arquivos `.json` na raiz

## Dados e Artefatos no Repositorio

- `queue.json`, `retry_queue.json`, `history.json`, `group_history.json` refletem estado recente
- `ptbrmerger.log` tambem esta na raiz
- Existe `.runtime-archive/` com snapshot de runtime
- Existem `__pycache__/` dentro de `src/` e `tests/`

## Observacoes Estruturais

- O repo nao esta "codigo puro"; ele tambem carrega ambiente de operacao e experimentacao
- Pastas relacionadas ao Codex/GSD ocupam espaco relevante mas nao fazem parte do produto final
- Para onboarding tecnico, vale filtrar mentalmente `src/`, `tests/`, `scripts/`, `README.md` e configuracoes antes de olhar o resto
