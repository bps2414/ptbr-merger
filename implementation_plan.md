# Plan: Fix Scoring Logic and qBittorrent Authentication

The goal is to ensure that the most relevant PT-BR release is selected regardless of minor fluctuations in Radarr's Custom Format scores, and to fix the connection to qBittorrent.

## Status da Implementação (Fase 2)

### O que foi implementado até agora:
- Nova lógica de score/peso multicamadas (high priority, indexer name, medium priority, WEB-DL).
- Retorno de múltiplos candidatos.

### Problemas de Coesão Resolvidos:
- [x] **PROBLEMA 1:** `ptbrmerger_min_score` movido pro final no `RadarrConfig` para evitar instabilidade.
- [x] **PROBLEMA 2:** `run_analyzer(trigger.py)` agora navega na nova listagem de dicionários retornada por `radarr_client`.
- [x] **PROBLEMA 3:** Fallback automatizado em `run_merger`: envia a próxima tag com a flag `exclude_titles` e autoinjeta no qBittorrent ao sofrer colisão `NOT_FOUND_STREAM`.
- [x] **PROBLEMA 4:** Login Bypass no qBittorrent usando Request em `app/version` testando ping de sessão efetiva de localhost.

### O que ainda falta da Fase 2 do PRD:
- Script de teste mock que irá injetar o array de Releases falsos e simular a pesagem automática.
- Execução Dry-Run local end-to-end com um arquivo `.mkv` validando o flow.

## User Review Required

> [!IMPORTANT]
> I will be lowering the default 'piso' (floor) for PT-BR releases from 15000 to 10000 to avoid filtering out valid releases that might have lower scores after Radarr updates.
> Also, please confirm if the qBittorrent credentials in [config.yml](file:///d:/ptbr-merger/config.yml) (`bps` / `14072010`) are indeed correct.

## Proposed Changes

### [Radarr Client] (src/radarr_client.py)

#### [MODIFY] [radarr_client.py](file:///d:/ptbr-merger/src/radarr_client.py)
 - Update [_calculate_secondary_score](file:///tmp/test_scoring.py#26-50) to use a tiered weighting system (Nível 4-0).
- Update [find_best_ptbr_release](file:///d:/ptbr-merger/src/radarr_client.py#132-223) to return a list of Top 5 candidates instead of a single URL.
- Add an `exclude_titles` parameter to [find_best_ptbr_release](file:///d:/ptbr-merger/src/radarr_client.py#132-223) to support retries.
- Lower score floor from 15000 to 10000.
- Enhance logging for scoring justification.

### [Configuration] (src/config.py & config.yml)

#### [MODIFY] [config.yml](file:///d:/ptbr-merger/config.yml)
 - Add `indexer_names_br` list.

#### [MODIFY] [config.py](file:///d:/ptbr-merger/src/config.py)
 - Update [PtbrKeywordsConfig](file:///tmp/test_scoring.py#4-12) dataclass to include `indexer_names_br`.

### [qBittorrent Client] (src/qbit_client.py)

#### [MODIFY] [qbit_client.py](file:///d:/ptbr-merger/src/qbit_client.py)
 - Add more descriptive error logging when [login()](file:///d:/ptbr-merger/src/qbit_client.py#14-45) fails.
 - Implement `Referer` header in `requests` calls to avoid auth rejection.

### [Trigger Mode] (src/trigger.py)

#### [MODIFY] [trigger.py](file:///d:/ptbr-merger/src/trigger.py)
 - Update [run_merger](file:///d:/ptbr-merger/src/trigger.py#75-153) (Bypass Mode): if `NOT_FOUND_STREAM` or sync error, identify the failed release and call [find_best_ptbr_release](file:///d:/ptbr-merger/src/radarr_client.py#132-223) again to get the next candidate.
 - Inject the next candidate into qBittorrent automatically.

## Verification Plan

### Automated Tests
- I'll create a mock test script in [/tmp/test_scoring.py](file:///tmp/test_scoring.py) that simulates the list of 68 releases with the scores and titles provided by the user, and verifies that the new logic picks the correct one.

### Manual Verification
1. Run `python src/trigger.py --dry-run --file-path "D:\path\to\some\4k.mkv"` to see which release it would pick now.
2. The user should verify the qBittorrent login by restarting the script after checking credentials.
