# Architecture

## Padrao Geral

A arquitetura e de script orquestrador com modulos de apoio, nao um servico web nem um dominio fortemente desacoplado. O centro de gravidade esta em `src/trigger.py`, que coordena leitura de evento, analise, busca, download, mux, validacao e limpeza.

## Fluxo Principal

1. `src/trigger.py` recebe evento do Radarr ou qBittorrent, ou execucao manual por CLI.
2. `src/analyzer.py` verifica se o 4K ja contem audio PT-BR.
3. Se faltar audio PT-BR, `src/radarr_client.py` busca e rankeia releases 1080p.
4. `src/qbit_client.py` injeta o release selecionado e administra deduplicacao/prioridade.
5. Quando o download termina, `src/trigger.py` resolve o arquivo 1080p concluido.
6. `src/analyzer.py` diagnostica sincronismo e `src/audio_fingerprint.py` pode refinar offset.
7. `src/merger.py` extrai audio, faz mux, valida e substitui o original.
8. `src/radarr_client.py` rescaneia o filme e aplica a tag de sucesso.
9. `src/notifier.py` mantem log local e webhook Discord durante o processo.

## Componentes

- Orquestracao: `src/trigger.py`
- Integracao externa: `src/radarr_client.py`, `src/qbit_client.py`, `src/bazarr_client.py`
- Midia e diagnostico: `src/analyzer.py`, `src/audio_fingerprint.py`, `src/merger.py`
- Estado local: `src/queue_manager.py`, `src/retry_queue_manager.py`, `src/history_manager.py`, `src/sync_intelligence.py`
- Comunicacao operacional: `src/notifier.py`
- Utilitarios CLI: `src/tools/*.py`

## Gerenciamento de Estado

Nao existe banco de dados. O estado operacional fica em JSONs na raiz:

- `queue.json` para controle do fluxo atual
- `retry_queue.json` para retries agendados
- `history.json` para trilha de eventos
- `group_history.json` para aprendizado de compatibilidade

Esse desenho privilegia simplicidade e portabilidade, mas deixa concorrencia, integridade e recuperacao mais sensiveis.

## Modelo de Controle

- Configuracao carregada uma vez por processo em `src/config.py`
- Clientes e managers sao inicializados em modulo global em `src/trigger.py` e `src/radarr_client.py`
- O codigo prefere funcoes a classes ricas; excecao parcial para managers e `QbitAddResult`

## Pontos de Entrada

- `src/trigger.py` via Radarr
- `src/trigger.py` via qBittorrent `OnDownloadComplete`
- `src/trigger.py --file-path ... --dry-run`
- `src/trigger.py --retry-pending`
- Ferramentas auxiliares em `src/tools/`

## Abstracoes Importantes

- Diagnostico de sync retorna um dicionario estruturado em `src/analyzer.py`
- Fingerprint tambem retorna categorias estruturadas em `src/audio_fingerprint.py`
- Ranking de release combina score do Radarr, heuristicas locais e historico em `src/radarr_client.py` + `src/sync_intelligence.py`

## Caracteristicas Arquiteturais

- Alto acoplamento a I/O local e servicos externos
- Orquestracao procedural e bem direta
- Boa observabilidade operacional para um script standalone
- Baixa separacao entre regras de negocio, infraestrutura e fluxo de aplicacao no modulo `src/trigger.py`
