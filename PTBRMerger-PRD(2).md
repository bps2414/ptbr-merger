# PTBRMerger — Product Requirements Document

**Versão:** 1.3  
**Data:** 22/03/2026  
**Status:** Planejamento — Radarr configurado  
**Stack:** Python 3.11+  
**Referências:** [Radarr Custom Scripts](https://wiki.servarr.com/radarr/custom-scripts) · [Radarr Settings](https://wiki.servarr.com/radarr/settings) · [trash-guides-ptbr](https://github.com/marcosviniciusi/trash-guides-ptbr)

---

## 1. Visão Geral

PTBRMerger é uma ferramenta de automação que injeta faixas de áudio PT-BR em releases 4K que não possuem dublagem brasileira. Ela é acionada automaticamente pelo Radarr quando um filme é importado, usa o próprio Radarr (com um perfil dedicado) para buscar e baixar a versão 1080p dual audio, extrai a faixa PT-BR via ffmpeg e a injeta no arquivo 4K original sem re-encoding.

### Problema

Releases 4K de alta qualidade raramente incluem áudio PT-BR. As versões dubladas/dual audio disponíveis nos trackers brasileiros geralmente estão em 1080p. O usuário precisa escolher entre qualidade técnica máxima (4K HDR) ou acessibilidade (PT-BR) — o PTBRMerger elimina esse trade-off.

### Solução

Automatizar o processo de:
1. Detectar filmes 4K sem faixa PT-BR
2. Encontrar a versão 1080p dual audio via Radarr (perfil dedicado com score mínimo PT-BR)
3. Extrair somente a faixa de áudio PT-BR com ffprobe+ffmpeg
4. Injetar no arquivo 4K original (zero re-encoding)
5. Limpar arquivos temporários

---

## 2. Arquitetura

### 2.1 Fluxo principal

```
[Radarr importa 4K]
        │
        ▼
[trigger.py recebe evento On Import via Custom Script]
        │
        ▼
[analyzer.py: ffprobe verifica se já tem PT-BR]
        │
   ┌────┴────┐
   │ tem     │ não tem
   ▼         ▼
[SKIPPED] [radarr_client.py: adiciona filme no perfil PTBRMerger]
          [rootFolderPath = D:\data\temp\ptbrmerger]
          [tag = ptbrmerger]
          [searchForMovie = True]
                    │
                    ▼
        [Radarr busca SOMENTE nos indexers com tag ptbrmerger]
        [Minimum Score = 24000 → rejeita releases sem PT-BR]
        [baixa 1080p dual em D:\data\temp\ptbrmerger\]
                    │
                    ▼
        [Radarr dispara segundo evento On Import]
                    │
                    ▼
        [trigger.py detecta path contém "ptbrmerger"]
                    │
                    ▼
        [analyzer.py: valida duração 4K vs 1080p]
        [diferença > 5s → SYNC_MISMATCH → aborta]
                    │
                    ▼
        [analyzer.py: confirma stream language=por existe]
        [não encontrou → NOT_FOUND_STREAM → aborta]
                    │
                    ▼
        [merger.py: extrai faixa PT-BR com ffmpeg]
        [merger.py: mux no arquivo 4K → output_tmp.mkv]
        [merger.py: substitui original pelo output]
                    │
                    ▼
        [cleanup: radarr_client remove filme PTBRMerger]
        [cleanup: qbit_client remove torrent 1080p temporário]
        [cleanup: deleta arquivos temp]
        [notifier: loga SUCCESS + Discord webhook]
                    │
                    ▼
              [FIM ✅]
```

### 2.2 Perfil PTBRMerger no Radarr

| Configuração | Valor | Motivo |
|---|---|---|
| Nome | `PTBRMerger` | identificado pelo script |
| Qualidades ativas | `Bluray-1080p`, `WEBDL-1080p`, `WEBRip-1080p` | só 1080p — só precisamos do áudio |
| Todas qualidades 2160p/4K | **Desativadas** | evita baixar 4K duplicado |
| Upgrades Allowed | Desativado | não precisa upgrade, só primeira versão PT-BR |
| Language | Any | CFs filtram PT-BR, não o campo Language |
| Minimum Custom Format Score | `24000` | rejeita qualquer release sem PT-BR |
| Upgrade Until Custom Format Score | `24000` | para na primeira versão PT-BR encontrada |

**Custom Format scores no perfil PTBRMerger:**

| Custom Format | Score | Resultado |
|---|---|---|
| Brazilian Group Tier - Dual Audio | +30000 | melhor opção — grupo BR bom + dual |
| Brazilian Dual Language | +29500 | dual audio confirmado |
| Brazilian Group Tier - Dubbed | +25000 | grupo BR bom + dublado |
| Brazilian Dubbed | +24000 | mínimo aceitável — passa o filtro |
| Brazilian Group Tier Bad | -10000 | derruba qualquer combinação abaixo de 24000 |
| LQ | -10000 | rejeita releases de baixa qualidade |
| Todos os outros CFs | 0 | irrelevantes para este perfil |

**Matemática do filtro — todos os cenários:**

| Combinação de CFs | Score total | Resultado |
|---|---|---|
| Dual Audio grupo bom | 30000 | ✅ aceito — melhor |
| Dual Language | 29500 | ✅ aceito |
| Dubbed grupo bom | 25000 | ✅ aceito |
| Dubbed simples | 24000 | ✅ aceito — mínimo |
| Grupo bad + Dual Audio | 30000 - 10000 = 20000 | ❌ rejeitado |
| Grupo bad + Dubbed | 24000 - 10000 = 14000 | ❌ rejeitado |
| LQ + Dubbed | 24000 - 10000 = 14000 | ❌ rejeitado |
| Sem PT-BR nenhum | 0 | ❌ rejeitado |

### 2.3 Tag `ptbrmerger` — condição e uso correto

Conforme documentação oficial do Radarr:

> "A Movie will use both indexers that have matching tags **and** indexers that have no tags."

Isso significa que a tag no **filme** sozinha não restringe nada. A restrição acontece quando a tag é aplicada nos **indexers**:

**Regra:** quando um filme tem a tag `ptbrmerger`, o Radarr usa os indexers com essa tag **mais** os indexers sem tag nenhuma.

Para isolar a busca PTBRMerger apenas aos indexers BR, é necessário:
1. Adicionar tag `ptbrmerger` nos indexers BR
2. Adicionar tag qualquer diferente (ex: `internacional`) nos indexers internacionais

Assim os indexers internacionais ficam invisíveis para a busca PTBRMerger.

**Onde configurar:**

| Indexer | Tag |
|---|---|
| Catálogo Betor | `ptbrmerger` |
| HDRTorrent | `ptbrmerger` |
| Rede Torrent | `ptbrmerger` |
| Apache Torrents | `ptbrmerger` |
| Torrentio | `internacional` ← qualquer tag diferente |
| 1337x / outros internacionais | `internacional` |

> Filmes normais (perfil HD) continuam usando todos os indexers porque não têm a tag `ptbrmerger` — o Radarr usa indexers com tag matching **e** indexers sem tag. Como os indexers BR têm a tag `ptbrmerger` e os internacionais têm `internacional`, nenhum deles fica sem tag — então filmes normais usam **todos** os indexers corretamente.

### 2.4 Como o trigger distingue os dois eventos

```
Evento 1 — import do 4K normal:
  radarr_movie_path        = D:\data\media\movies\Sonic (2024)
  radarr_moviefile_quality = Remux-2160p
  radarr_movie_tags        = (vazio)

Evento 2 — import do 1080p PTBRMerger:
  radarr_movie_path        = D:\data\temp\ptbrmerger\Sonic (2024)
  radarr_moviefile_quality = WEBDL-1080p
  radarr_movie_tags        = ptbrmerger
```

O trigger usa **duas verificações** para máxima segurança:

```python
is_merger_event = (
    "ptbrmerger" in movie_path.lower() or
    "ptbrmerger" in movie_tags.lower()
)
```

---

## 3. Módulos

### 3.1 trigger.py
**Responsabilidade:** Entry point. Recebe eventos do Radarr via env vars.

```python
import os, sys

movie_path = os.environ.get("radarr_movie_path", "")
event_type = os.environ.get("radarr_eventtype", "")
movie_tags = os.environ.get("radarr_movie_tags", "")
file_path  = os.environ.get("radarr_moviefile_path", "")
tmdb_id    = os.environ.get("radarr_movie_tmdbid", "")
movie_id   = os.environ.get("radarr_movie_id", "")
title      = os.environ.get("radarr_movie_title", "")
year       = os.environ.get("radarr_movie_year", "")

if event_type == "Test":
    sys.exit(0)  # ignora graciosamente

if event_type != "Download":
    sys.exit(0)

is_merger_event = (
    "ptbrmerger" in movie_path.lower() or
    "ptbrmerger" in movie_tags.lower()
)

if is_merger_event:
    run_merger(file_path, movie_id, tmdb_id)
else:
    run_analyzer(file_path, tmdb_id, title, year)
```

### 3.2 analyzer.py
**Responsabilidade:** Inspecionar arquivo com ffprobe.

Funções:
- `has_ptbr_audio(filepath)` → bool
  - Verifica streams de áudio com `tags.language` em `["por", "pt", "pt-br", "pt-BR", "portuguese"]`
  - True → `SKIPPED_HAS_PTBR`
- `get_duration(filepath)` → float (segundos)
- `get_ptbr_stream_index(filepath)` → int | None
  - Itera **todos** os streams — não assume posição fixa
  - None → `NOT_FOUND_STREAM`
- `validate_sync(file_4k, file_1080p)` → bool
  - Diferença > 5s → False → `SYNC_MISMATCH`
  - Loga diferença exata para debug

### 3.3 radarr_client.py
**Responsabilidade:** Wrapper da API do Radarr v3.

```python
# Busca ID do perfil PTBRMerger
GET /api/v3/qualityprofile
→ filtra por name == "PTBRMerger"

# Busca ID da tag ptbrmerger
GET /api/v3/tag
→ filtra por label == "ptbrmerger"

# Adiciona filme no perfil PTBRMerger
POST /api/v3/movie
{
    "tmdbId": tmdb_id,
    "title": title,
    "year": year,
    "qualityProfileId": ptbrmerger_profile_id,
    "rootFolderPath": "D:\\data\\temp\\ptbrmerger",
    "monitored": True,
    "tags": [ptbrmerger_tag_id],
    "addOptions": {
        "searchForMovie": True
    }
}

# Remove filme e arquivos temp
DELETE /api/v3/movie/{movie_id}?deleteFiles=true&addImportExclusion=false

# Rescan do filme 4K original após mux
POST /api/v3/command
{"name": "RescanMovie", "movieId": original_movie_id}
```

Funções:
- `get_profile_id(profile_name)` → int
- `get_tag_id(tag_name)` → int
- `get_movie_by_tmdbid(tmdb_id)` → dict | None
- `add_movie_ptbrmerger(tmdb_id, title, year)` → int (movie_id)
- `remove_movie_ptbrmerger(movie_id)` → void
- `rescan_movie(movie_id)` → void

### 3.4 qbit_client.py
**Responsabilidade:** Remover torrent temporário do qBittorrent após mux.

```python
# Login
POST /api/v2/auth/login
body: username=admin&password=senha

# Remove torrent e arquivos
POST /api/v2/torrents/delete
body: hashes={hash}&deleteFiles=true
```

O hash do torrent vem de `radarr_download_id` — variável de ambiente enviada pelo Radarr no evento On Import.

Funções:
- `login()` → salva cookie de sessão
- `remove_torrent(torrent_hash, delete_files=True)` → void

### 3.5 merger.py
**Responsabilidade:** Extrair áudio PT-BR e muxar no 4K.

```bash
# Extrai faixa PT-BR do 1080p (sem re-encode)
ffmpeg -i filme_1080p.mkv -map 0:a:{idx} -c:a copy audio_ptbr.eac3

# Mux: PT-BR como primeira faixa, original depois, legendas preservadas
ffmpeg -i 4k.mkv -i audio_ptbr.eac3 \
  -map 0:v -map 1:a -map 0:a -map 0:s \
  -c copy \
  -metadata:s:a:0 language=por \
  -metadata:s:a:0 title="Português (Brasil)" \
  4k_output_tmp.mkv
```

`replace_original()` usa `os.replace()` (atômico) e **só executa** se `output_tmp.mkv` existir e tiver tamanho > 0.

### 3.6 notifier.py

Estados:
- `SUCCESS` — mux concluído
- `SKIPPED_HAS_PTBR` — já tinha PT-BR
- `NOT_FOUND` — Radarr não achou release PT-BR
- `NOT_FOUND_STREAM` — DUAL no título mas sem stream `language=por`
- `SYNC_MISMATCH` — duração difere > 5s
- `DUPLICATE_CALL` — merger já em andamento para esse filme
- `ERROR` — erro inesperado

### 3.7 config.py

```yaml
radarr:
  url: http://localhost:7878
  api_key: SUA_KEY
  ptbrmerger_profile_name: PTBRMerger
  ptbrmerger_root_folder: D:\data\temp\ptbrmerger
  ptbrmerger_tag_name: ptbrmerger

qbittorrent:
  url: http://localhost:8080
  username: admin
  password: senha

ffmpeg:
  ffmpeg_path: ffmpeg
  ffprobe_path: ffprobe

sync:
  max_duration_diff_seconds: 5

notifications:
  discord_webhook_url: ""

logging:
  level: INFO
  file: D:\ptbr-merger\ptbrmerger.log
```

---

## 4. Estrutura de arquivos

```
D:\ptbr-merger\
├── src\
│   ├── trigger.py          ← entry point chamado pelo Radarr
│   ├── analyzer.py         ← ffprobe — detecta e valida áudios
│   ├── radarr_client.py    ← wrapper API Radarr v3
│   ├── qbit_client.py      ← wrapper API qBittorrent
│   ├── merger.py           ← ffmpeg extract + mux
│   ├── notifier.py         ← logs + Discord
│   └── config.py           ← lê config.yml
├── config.yml
├── requirements.txt
├── install.ps1
└── ptbrmerger.log          ← gerado em runtime
```

---

## 5. Configuração no Radarr (ordem exata)

### 5.1 Instalar ffmpeg
```powershell
winget install ffmpeg
ffmpeg -version
ffprobe -version
```

### 5.2 Criar pasta temporária
```powershell
mkdir D:\data\temp\ptbrmerger
```

### 5.3 Adicionar Root Folder temporário
Radarr → **Settings → Media Management → Root Folders → Add** → `D:\data\temp\ptbrmerger`

> Deve estar no mesmo disco que `D:\data\media\movies` para hardlinks funcionarem.

### 5.4 Criar tags
Radarr → **Settings → Tags → Add**:
- `ptbrmerger`
- `internacional`

### 5.5 Adicionar tags nos indexers

| Indexer | Tag |
|---|---|
| Catálogo Betor | `ptbrmerger` |
| HDRTorrent | `ptbrmerger` |
| Rede Torrent | `ptbrmerger` |
| Apache Torrents | `ptbrmerger` |
| Torrentio | `internacional` |
| Outros internacionais | `internacional` |

### 5.6 Criar Quality Profile `PTBRMerger`
Radarr → **Settings → Profiles → Quality Profiles → +**

Configurações conforme seção 2.2. Scores conforme tabela de CFs.

### 5.7 Configurar Custom Script
Radarr → **Settings → Connect → + → Custom Script**

| Campo | Valor |
|---|---|
| Name | `PTBRMerger` |
| On Import | ✅ |
| On Upgrade | ✅ |
| Todos os outros | ✗ |
| Tags | Vazio — roda para todos os filmes |
| Path | `python` |
| Arguments | `D:\ptbr-merger\src\trigger.py` |

> Após salvar, clicar em **Test**. O script receberá `radarr_eventtype=Test` e deve retornar exit code 0 graciosamente.

### 5.8 Download Client
Radarr → **Settings → Download Clients → qBittorrent** → `Remove Completed` → **Desativado**

> O script precisa que o arquivo 1080p ainda exista no qBittorrent após o import para extrair o áudio. O `qbit_client.py` faz o cleanup manualmente após o mux.

---

## 6. Edge Cases

| Edge Case | Detecção | Comportamento |
|---|---|---|
| 4K já tem PT-BR | `has_ptbr_audio()` → True | `SKIPPED_HAS_PTBR` |
| DUAL no título mas idioma JA/EN | `get_ptbr_stream_index()` → None | `NOT_FOUND_STREAM` → aborta → deleta temp |
| Radarr não acha release PT-BR | Timeout sem segundo evento | `NOT_FOUND` → remove filme do PTBRMerger |
| 1080p é corte diferente do 4K | `validate_sync()` → diferença > 5s | `SYNC_MISMATCH` → aborta → loga diferença |
| Trigger chamado duas vezes | tmdbId já no perfil PTBRMerger | `DUPLICATE_CALL` → ignora |
| ffmpeg falha no meio | output_tmp incompleto | `replace_original()` valida tamanho → mantém original |
| Múltiplas faixas PT-BR no 1080p | `get_ptbr_stream_index()` → lista | Usa o primeiro stream PT-BR |
| Path com espaços/caracteres especiais | Sempre | `subprocess` com lista de args, nunca `shell=True` |
| Evento `Test` do Radarr | `eventtype == "Test"` | `sys.exit(0)` imediato |
| Radarr faz upgrade do 4K | `isupgrade == "True"` | Trata igual a import normal |

---

## 7. Riscos gerais

| Risco | Severidade | Mitigação |
|---|---|---|
| Áudio fora de sincronia | Alta | `validate_sync()` com threshold 5s |
| DUAL = idioma errado | Alta | `ffprobe` verifica `language=por` no stream |
| Output corrompido substitui original | Alta | Valida tamanho antes de `os.replace()` |
| Sem release PT-BR disponível | Média | Encerra graciosamente, Bazarr cobre com legenda |
| Espaço em disco | Média | Cleanup em `finally` |
| Chamada dupla do trigger | Baixa | Verificação via API do Radarr |

---

## 8. Fases de desenvolvimento

### Fase 1 — MVP
- [ ] `config.py`
- [ ] `trigger.py`
- [ ] `analyzer.py`
- [ ] `radarr_client.py`
- [ ] `qbit_client.py`
- [ ] `merger.py`
- [ ] `notifier.py` — só log em arquivo
- [ ] Radarr configurado manualmente (seção 5)

### Fase 2 — Robustez
- [ ] Retry com exponential backoff nas APIs
- [ ] Proteção contra `DUPLICATE_CALL`
- [ ] Notificação Discord
- [ ] Modo manual: `python trigger.py --file-path "D:\..."`
- [ ] Timeout para aguardar Radarr encontrar release

### Fase 3 — Polish
- [ ] `setup.py` — configura Radarr automaticamente via API
- [ ] Interface web com histórico de merges
- [ ] Fila para reprocessar biblioteca existente
- [ ] Publicar no GitHub com README PT-BR

---

## 9. Dependências

```
requests>=2.31.0
PyYAML>=6.0
loguru>=0.7.0
ffmpeg-python>=0.2.0
```

Requisitos externos: Python 3.11+, ffmpeg no PATH, Radarr configurado.

---

## 10. Implementação — detalhes técnicos

### 10.1 ffprobe — estrutura JSON esperada

```json
{
  "streams": [
    {
      "index": 0,
      "codec_type": "video",
      "codec_name": "hevc"
    },
    {
      "index": 1,
      "codec_type": "audio",
      "codec_name": "eac3",
      "channels": 6,
      "tags": {
        "language": "por",
        "title": "Português (Brasil)"
      }
    },
    {
      "index": 2,
      "codec_type": "audio",
      "codec_name": "eac3",
      "tags": {
        "language": "eng",
        "title": "English"
      }
    }
  ],
  "format": {
    "duration": "6842.123000"
  }
}
```

Comando exato usado pelo `analyzer.py`:
```bash
ffprobe -v quiet -print_format json -show_streams -show_format "arquivo.mkv"
```

Tags de idioma PT-BR aceitas: `["por", "pt", "pt-br", "pt-BR", "portuguese"]`

### 10.2 State persistence — recuperação de falha

**Problema:** se o script crashar entre o download do 1080p e o mux, na próxima execução o `radarr_client.add_movie_ptbrmerger()` vai tentar adicionar um filme que já existe no Radarr → erro 400.

**Solução — verificar antes de adicionar:**

```python
# Em radarr_client.add_movie_ptbrmerger():
existing = get_movie_by_tmdbid(tmdb_id)
if existing and existing.get("qualityProfileId") == ptbrmerger_profile_id:
    # Filme já está no perfil PTBRMerger — merger em andamento ou travado
    # Verifica se tem arquivo na pasta temp
    if arquivo_existe_em_temp(tmdb_id):
        # Retoma do passo do mux diretamente
        return existing["id"], RESUME_FROM_MUX
    else:
        # Está monitorado mas sem arquivo — aguarda Radarr baixar
        return existing["id"], WAITING_DOWNLOAD
```

**Definição de `arquivo_existe_em_temp(tmdb_id)`:**

```python
def arquivo_existe_em_temp(tmdb_id: str) -> Path | None:
    """
    Busca qualquer arquivo .mkv dentro de ptbrmerger_root_folder.
    Retorna o Path do arquivo se encontrar, None se não encontrar.
    Não depende do nome — varre toda a pasta temp recursivamente.
    """
    temp_folder = Path(config.radarr.ptbrmerger_root_folder)
    mkv_files = list(temp_folder.rglob("*.mkv"))
    if mkv_files:
        return mkv_files[0]  # retorna o primeiro encontrado
    return None
```

### 10.3 Instalação e setup

`install.ps1`:
```powershell
pip install -r requirements.txt
# Valida que o script carrega sem erro (sem env vars do Radarr, só testa imports)
python -c "import src.trigger; print('OK')"
```

`requirements.txt`:
```
requests>=2.31.0
PyYAML>=6.0
loguru>=0.7.0
ffmpeg-python>=0.2.0
```

### 10.4 Path handling — sempre usar pathlib

Todo o projeto usa `pathlib.Path` em vez de strings para paths. Nunca concatenar paths com `+` ou `\\`.

```python
from pathlib import Path

# Correto
temp_folder = Path(config.radarr.ptbrmerger_root_folder)
audio_tmp   = temp_folder / "audio_ptbr.eac3"
output_tmp  = Path(file_4k).parent / "output_tmp.mkv"

# Errado
temp_folder = config.radarr.ptbrmerger_root_folder + "\\audio_ptbr.eac3"
```

Ao passar paths para `subprocess`/ffmpeg, sempre converter com `str(path)`.

### 10.5 Dry-run e testes

O script suporta modo `--dry-run` que executa tudo exceto o mux e substituição do arquivo:

```bash
python src\trigger.py --dry-run
```

Em dry-run:
- `analyzer.py` roda normalmente — loga o que encontrou
- `radarr_client.py` roda normalmente — adiciona no PTBRMerger
- `merger.py` **não roda** — loga o comando ffmpeg que seria executado
- `qbit_client.py` **não roda** — loga o hash que seria removido

Variável de ambiente alternativa para dry-run (útil para testes):
```bash
set PTBRMERGER_DRY_RUN=true
python src\trigger.py
```

---

## 11. Critérios de sucesso

- Filme 4K sem PT-BR → arquivo final com faixa PT-BR como primeira faixa de áudio
- Arquivo 4K original nunca corrompido em nenhum cenário de erro
- Todos os edge cases da seção 6 cobertos com log claro
- Zero intervenção manual para filmes onde release PT-BR existe nos indexers BR
- Processo completo em menos de 2 horas
