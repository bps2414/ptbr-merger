# Setup local

## Requisitos

- Python 3.11 ou superior
- FFmpeg e FFprobe acessiveis pelo sistema ou configurados em `config.yml`
- Windows para usar os atalhos `.bat`
- Radarr, qBittorrent, Discord e Bazarr somente se for usar a automacao externa

## Instalacao

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Crie a configuracao local:

```bat
copy config.example.yml config.yml
```

Edite `config.yml` com os caminhos corretos de `ffmpeg_path` e `ffprobe_path`.

## Modo web local

```bat
START_PTBRMERGER.bat
```

Ou:

```bash
python -m src.web.server
```

A aplicacao abre em:

```text
http://127.0.0.1:8787
```

## Validacao do ambiente

```bash
python -m src.tools.preflight --json
```

Se Radarr ou qBittorrent aparecerem como pendentes, isso nao bloqueia o workflow manual. Para gerar MKV local, FFmpeg e FFprobe sao as dependencias essenciais.

## Arquivos locais

Arquivos gerados durante uso normal ficam fora do Git:

- `config.yml`
- `.env`
- `input/`
- `output/`
- `workdir/`
- `reports/`
- `recipes/`
- `logs/`
- `queue.json`
- `retry_queue.json`
- `history.json`
- `group_history.json`
- `ptbrmerger.log`

Nao coloque tokens, senhas, chaves de API ou webhooks em arquivos versionados.
