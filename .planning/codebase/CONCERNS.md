# Concerns

## Resumo

O projeto parece funcional e relativamente bem testado, mas carrega alguns riscos tipicos de automacao local: alto acoplamento, muito estado em arquivo JSON e um modulo orquestrador gigante que vira ponto unico de tensao.

## Maiores Riscos Tecnicos

- `src/trigger.py` esta muito grande e centraliza fluxo, estado, fallback, retry, notificacao e cleanup. Isso dificulta manutencao e aumenta risco de regressao.
- `src/radarr_client.py` tambem concentra muita regra de negocio e heuristica de ranking num unico modulo.
- Configuracao singleton global em `src/config.py` simplifica o uso, mas complica isolamento e composicao em runtime.

## Estado e Confiabilidade

- `queue.json`, `retry_queue.json`, `history.json` e `group_history.json` sao simples e praticos, mas nao oferecem protecao contra concorrencia real nem corrupcao por escrita interrompida.
- O repositorio mistura codigo-fonte com estado operacional atual. Isso e util no desktop, mas perigoso para higiene do projeto e reproducibilidade.
- Existe `config.yml` no workspace. Mesmo que o projeto suporte env vars, isso merece atencao constante para nao vazar configuracao sensivel.

## Acoplamento a Ambiente

- O fluxo depende de Radarr, qBittorrent, FFmpeg e possivelmente Bazarr locais.
- `run.bat` aponta para um caminho Python bem especifico do host atual.
- Alguns scripts e exemplos pressupem Windows de forma explicita.

## Sinais de Divida Tecnica

- Problemas de encoding aparecem em varios outputs lidos do terminal, especialmente textos com acentos em `src/trigger.py` e `src/notifier.py`.
- O repo contem `__pycache__/`, arquivos de log e archive de runtime no workspace, o que polui o mapa mental e pode atrapalhar diffs.
- Pastas `.codex*` e pacote `.tgz` convivem com o produto; para operacao local tudo bem, mas para manutencao isso adiciona ruido.

## Riscos Funcionais

- Heuristicas de PT-BR e scoring em `src/radarr_client.py` sao poderosas, mas muito dependentes de nomenclatura externa e podem ficar frageis diante de novos indexers.
- Fingerprint de audio em `src/audio_fingerprint.py` depende de parametros delicados e custo computacional adicional.
- Replace do arquivo final e uma operacao destrutiva; existe validacao previa, mas qualquer edge case em duracao/stream merece respeito, mano.

## Gaps de Produto/Processo

- Nao encontrei evidencia de CI, lint ou formatacao automatica.
- Nao ha separacao forte entre "biblioteca" e "app"; para evolucao maior, isso pode travar.
- O projeto parece operar em um unico processo/host. Escalonar ou paralelizar exigiria repensar persistencia e locks.

## Boas Noticias no Meio do Caos

- A suite de testes existe e cobre bastante coisa
- Ferramentas operacionais em `src/tools/` mostram preocupacao real com suporte
- O pipeline tenta registrar historico e falhar de modo explicavel, o que salva muita pele em automacao desse tipo

## Prioridades de Endurecimento

1. Fatiar `src/trigger.py` em etapas ou servicos menores.
2. Isolar regras de ranking do `src/radarr_client.py` em modulos dedicados.
3. Melhorar higiene do repositorio separando runtime de codigo.
4. Padronizar encoding e revisar textos/logs.
5. Garantir validacao automatica continua com CI.
