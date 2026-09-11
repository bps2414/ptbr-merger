# PTBRMerger

![Marca do PTBRMerger](src/web/static/assets/ptbrmerger-mark.svg)

PTBRMerger e uma ferramenta local, Windows-first, para inspecionar arquivos MKV e adicionar audio preferido em PT-BR com apoio de FFmpeg/FFprobe. O projeto tambem preserva um fluxo de automacao com Radarr e qBittorrent para ambientes de midia local.

> 🚀 **Procurando a V2 Autônoma para Servidores Linux / Homelab?**  
> Conheça a pasta [`v2/`](./v2/README.md), uma arquitetura de alta performance com suporte a multi-instância Radarr (4K + Doador), sincronização espectral milimétrica via RedSync, SSD staging buffer, proteção de hardware de disco (Seed Guard) e notificações granulares no Discord.

## Status do projeto

Projeto funcional em evolucao. A base atual possui:

- interface web local em `http://127.0.0.1:8787`;
- workflow manual para alvo MKV + fonte MKV com audio PT-BR;
- pipeline legado com Radarr, qBittorrent, Discord e Bazarr opcional;
- testes automatizados para regras de negocio, integracoes simuladas, snapshots de API e fixtures de midia sintetica.

Nao ha deploy publico porque a aplicacao foi desenhada para rodar localmente e lidar com arquivos da maquina do usuario.

## Problema que resolve

Em bibliotecas locais de midia, e comum ter um arquivo de melhor qualidade sem audio PT-BR e outro arquivo compativel com o audio desejado. O PTBRMerger ajuda a analisar, sincronizar, muxar e validar esse resultado sem depender de um servico em nuvem.

## Principais funcionalidades

- Interface web local vinculada a `127.0.0.1`.
- Criacao automatica das pastas `input/`, `output/`, `workdir/`, `reports/`, `recipes/` e `logs/`.
- Inspecao de streams via `ffprobe`.
- Deteccao de audio PT-BR por idioma, titulo e metadados.
- Plano seguro antes da geracao do arquivo final.
- Mux de audio usando `ffmpeg`.
- Relatorios e receitas locais para auditar o que foi feito.
- Preflight operacional para validar dependencias e servicos externos.
- Integracao opcional com Radarr, qBittorrent, Discord e Bazarr.
- Fila, historico e retry local via arquivos JSON ignorados pelo Git.

## Stack utilizada

- Python 3.11+
- FFmpeg e FFprobe
- Pytest
- `requests`
- `PyYAML`
- `loguru`
- `numpy`
- HTML, CSS e JavaScript sem framework para a interface local
- Radarr, qBittorrent, Discord Webhook e Bazarr como integracoes opcionais

## Como rodar localmente

Clone o repositorio e instale as dependencias:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Copie o template de configuracao:

```bash
copy config.example.yml config.yml
```

Edite `config.yml` com os caminhos locais do FFmpeg/FFprobe e, se for usar automacao externa, com os dados do Radarr, qBittorrent, Discord e Bazarr.

Para abrir o modo web local no Windows:

```bat
START_PTBRMERGER.bat
```

Ou rode diretamente:

```bash
python -m src.web.server
```

Depois acesse:

```text
http://127.0.0.1:8787
```

Fluxo manual recomendado:

1. Coloque o MKV alvo e o MKV fonte em `input/`.
2. Clique em `Atualizar input`.
3. Selecione os arquivos.
4. Use `Detectar faixas`.
5. Crie o plano seguro.
6. Gere o MKV final em `output/`.

## Variaveis de ambiente

O projeto pode ler algumas configuracoes sensiveis por variaveis de ambiente, sobrescrevendo `config.yml` quando elas estiverem definidas.

Use `.env.example` apenas como referencia de nomes. Nunca versionar `.env` real.

```text
RADARR_URL
RADARR_API_KEY
QBITTORRENT_URL
QBITTORRENT_USERNAME
QBITTORRENT_PASSWORD
DISCORD_WEBHOOK_URL
```

## Scripts principais

```bash
pytest -q
python -m compileall src tests
python -m src.tools.preflight --json
python -m src.tools.status
python -m src.tools.runtime_hygiene --json
python -m src.tools.refresh_webhook --tmdb <TMDB_ID>
python src/trigger.py --dry-run --file-path "D:\Movies\Filme.mkv"
```

Atalhos Windows:

```bat
START_PTBRMERGER.bat
scripts\preflight.bat
scripts\status.bat
scripts\watch-log.bat
scripts\runtime-hygiene.bat
scripts\refresh-webhook.bat
```

## Estrutura do projeto

```text
src/
  analyzer.py                  analise de streams, duracao e diagnostico de sync
  merger.py                    extracao, mux e validacao final com FFmpeg
  trigger.py                   entrada principal para automacao Radarr/qBittorrent
  radarr_client.py             busca, ranking e comandos do Radarr
  qbit_client.py               integracao com qBittorrent
  notifier.py                  logs e notificacoes Discord
  tools/                       comandos operacionais
  web/                         servidor e interface local
  workflows/                   workflow manual de audio preferido
  storage/                     persistencia local de jobs e receitas
tests/
  test_*.py                    suite automatizada
  support/                     helpers de fixtures e snapshots
  test_data/                   dados sanitizados para testes
scripts/
  *.bat e utilitarios Python   atalhos e ferramentas auxiliares
docs/
  OVERVIEW.md                  visao geral do projeto
  SETUP.md                     configuracao e execucao local
  ROADMAP.md                   proximos passos realistas
```

## Decisoes tecnicas relevantes

- Local-first: a aplicacao roda na maquina do usuario e nao exige conta em nuvem.
- Segurança operacional: o modo web manual nao substitui o arquivo original.
- Automacao separada do fluxo manual: Radarr/qBittorrent continuam disponiveis, mas o uso local basico nao depende deles.
- Configuracao sensivel fora do Git: `config.yml`, `.env`, logs, filas e historicos sao ignorados.
- Testes com fixtures sinteticas: a suite valida comportamento de midia sem baixar filmes reais.
- Interface simples: HTML/CSS/JS puro reduzem dependencia de build frontend.

## Para avaliadores

Este projeto demonstra habilidade em automacao local, integracao com APIs, manipulacao segura de arquivos de midia e criacao de ferramentas operacionais.

Pontos interessantes para observar:

- `src/trigger.py`, `src/radarr_client.py` e `src/qbit_client.py` mostram orquestracao com servicos externos.
- `src/analyzer.py`, `src/merger.py` e `src/audio_fingerprint.py` concentram a parte de midia, validacao e sincronismo.
- `src/web/` mostra uma interface local sem backend pesado.
- `src/tools/preflight.py` e `src/tools/runtime_hygiene.py` mostram preocupacao com operacao real.
- `tests/` cobre regras de negocio, payloads externos, workflows e cenarios com fixtures.

Decisoes tomadas:

- manter o produto local para evitar exposicao desnecessaria de arquivos e credenciais;
- gerar planos antes de executar operacoes destrutivas ou caras;
- manter historico e relatorios para facilitar diagnostico;
- deixar integracoes externas opcionais no modo manual.

Em uma proxima versao, eu priorizaria quebrar `src/trigger.py` em servicos menores, adicionar pipeline CI, melhorar a cobertura de casos reais de FFmpeg em diferentes ambientes e publicar screenshots atualizados da interface.

## Roadmap curto

- Adicionar CI para rodar testes e `compileall` em pull requests.
- Melhorar a separacao interna do orquestrador principal.
- Criar screenshots versionadas da interface web local.
- Refinar mensagens de erro para usuarios nao tecnicos.
- Documentar exemplos de configuracao por ambiente.

## Melhorias futuras

- Assistente guiado para recovery manual.
- Exportacao mais amigavel de relatorios.
- Mais perfis de idioma alem do PT-BR.
- Observabilidade melhor para execucoes longas.
- Instalacao local mais simples das dependencias de midia.

## Licenca

Este repositorio ainda nao declara uma licenca. Antes de publicar para uso de terceiros, adicione uma licenca adequada ao objetivo do projeto.

## Autor

Projeto mantido pelo proprietario do repositorio.
