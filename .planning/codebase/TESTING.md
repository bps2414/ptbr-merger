# Testing

## Resumo

A base possui uma suite de testes bem mais robusta do que um script standalone comum. O foco parece ser confiabilidade de integracoes, heuristicas de ranking e ferramentas operacionais.

## Framework e Execucao

- Framework: `pytest`
- Comando principal descrito no `README.md`: `pytest -q`
- Verificacao adicional documentada: `python -m compileall src tests`

## Organizacao

Testes vivem em `tests/` e seguem o padrao `test_<modulo>.py`.

Arquivos centrais:

- `tests/test_trigger.py`
- `tests/test_radarr_client.py`
- `tests/test_qbit_client.py`
- `tests/test_analyzer.py`
- `tests/test_merger.py`
- `tests/test_notifier.py`
- `tests/test_sync_intelligence.py`
- `tests/test_tools.py`
- `tests/test_media_integration.py`
- `tests/test_api_snapshots.py`

## Tipos de Teste

- Unitarios para managers e config
- Testes de integracao simulada com mocks HTTP
- Testes de fluxo da orquestracao em `tests/test_trigger.py`
- Testes de compatibilidade de payload por snapshot em `tests/test_api_snapshots.py`
- Testes com fixtures de midia sintetica em `tests/test_media_integration.py`

## Infra de Teste

- `tests/support/api_snapshots.py`: helpers para snapshots sanitizados
- `tests/support/media_fixtures.py`: helpers de fixtures de midia
- `tests/test_data/api_snapshots/`: corpus de payloads
- `tests/test_data/media_fixtures/`: manifesto do corpus sintetico

## Tecnicas Usadas

- `patch` massivo em clientes externos e subprocessos
- `tmp_path` para isolar `queue.json`, `history.json`, `retry_queue.json` e logs
- Uso de `SimpleNamespace` para configs fake em testes de ferramentas

## Pontos Fortes

- Boa cobertura das regras de selecao de release em `tests/test_radarr_client.py`
- Cobertura do caminho feliz e cenarios de offset/fingerprint em `tests/test_trigger.py`
- Cobertura das ferramentas operacionais em `tests/test_tools.py`
- Valida compatibilidade contra drift de payload externo

## Riscos de Teste

- Nao ha indicao de pipeline CI no material inspecionado
- Parte relevante depende de mocks, entao regressao de integracao real ainda pode escapar
- Dependencias de `ffmpeg`/`ffprobe` podem dificultar repetibilidade fora do ambiente esperado

## Arquivos para Revisar ao Adicionar Testes

- `tests/test_trigger.py` para fluxo principal
- `tests/test_radarr_client.py` para ranking/filtros
- `tests/test_tools.py` para utilitarios
- `tests/test_media_integration.py` quando a mudanca tocar mux, stream ou sincronismo
