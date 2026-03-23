# PTBRMerger MVP Plan

## Visão Geral
Sistema de injeção automática de faixa de áudio PT-BR em arquivos 4K via download auxiliar de 1080p DUAL no Radarr.

## 1. Ordem de Implementação dos Módulos (Top-down Architecture / Bottom-up Implementation)
A implementação será feita debaixo para cima, garantindo que módulos independentes sejam criados e testados antes de integrar no fluxo principal.

1. **`config.py`**
2. **`notifier.py`**
3. **`qbit_client.py`**
4. **`radarr_client.py`**
5. **`analyzer.py`**
6. **`merger.py`**
7. **`trigger.py`**

## 2. Funções Expostas e Dependências por Módulo

### 1. `config.py`
* **Responsabilidade:** Parsing do arquivo YAML de configurações.
* **Funções/Variáveis Expostas:**
  * Objeto dinâmico/estruturado das opções de `radarr`, `qbittorrent`, `ffmpeg`, `sync`, `notifications` e `logging`.
* **Dependências:** `PyYAML`, `os`, `pathlib`

### 2. `notifier.py`
* **Responsabilidade:** Registro de logs com `loguru` (nesta fase 1, Discord só na Fase 2 mas módulo é base).
* **Funções Expostas:**
  * Métodos rápidos de proxy global: `info(msg)`, `error(msg)`, `warning(msg)`, `success(msg)`
  * `notify_status(status_code, context)`
* **Dependências:** `config.py`, `loguru`

### 3. `qbit_client.py`
* **Responsabilidade:** Cliente HTTP para API do qBittorrent.
* **Funções Expostas:**
  * `remove_torrent(torrent_hash: str, delete_files: bool = True) -> None`
* **Dependências:** `config.py`, `requests`, `notifier.py`

### 4. `radarr_client.py`
* **Responsabilidade:** Integração com a API V3 do Radarr.
* **Funções Expostas:**
  * `get_profile_id(profile_name: str) -> int`
  * `get_tag_id(tag_name: str) -> int`
  * `get_movie_by_tmdbid(tmdb_id: str) -> dict | None`
  * `add_movie_ptbrmerger(tmdb_id: str, title: str, year: str) -> int`
  * `remove_movie_ptbrmerger(movie_id: int) -> None`
  * `rescan_movie(movie_id: int) -> None`
  * `arquivo_existe_em_temp(tmdb_id: str) -> Path | None`
* **Dependências:** `config.py`, `requests`, `pathlib`, `notifier.py`

### 5. `analyzer.py`
* **Responsabilidade:** Análise técnica de codecs via `ffprobe`.
* **Funções Expostas:**
  * `has_ptbr_audio(filepath: Path) -> bool`
  * `get_ptbr_stream_index(filepath: Path) -> int | None`
  * `get_duration(filepath: Path) -> float`
  * `validate_sync(file_4k: Path, file_1080p: Path) -> bool`
* **Dependências:** `config.py`, `subprocess` (para invocar ffmpeg nativo), `pathlib`, `json`, `notifier.py`

### 6. `merger.py`
* **Responsabilidade:** Extração de áudio e injeção sem perda de qualidade (muxing).
* **Funções Expostas:**
  * `extract_audio(file_1080p: Path, stream_idx: int, output_audio: Path) -> None`
  * `mux_audio(file_4k: Path, audio_ptbr: Path, output_tmp: Path) -> None`
  * `replace_original(output_tmp: Path, file_4k: Path) -> None`
* **Dependências:** `config.py`, `subprocess`, `pathlib`, `os`, `notifier.py`

### 7. `trigger.py`
* **Responsabilidade:** Controlador principal e entry-point invocado pelo Radarr on-import.
* **Funções Expostas:**
  * `main()`
  * `run_analyzer(file_path, tmdb_id, title, year)`
  * `run_merger(file_path, ptbrmerger_movie_id, tmdb_id)`
* **Dependências:** `sys`, `os`, `analyzer.py`, `radarr_client.py`, `qbit_client.py`, `merger.py`, `notifier.py`, `config.py`

## 3. Ambiguidades e Decisões Técnicas Identificadas no PRD

1. **Bug do FFmpeg com ausência de Legendas:** 
   O comando ffmpeg no PRD mostra o mapa `-map 0:s`. Mas e se o vídeo original não tiver legendas nativas? O ffmpeg falhará imediatamente se tentar mapear `-map 0:s` e não houver stream `s`.
   * **Decisão:** Usar a tratativa de streams opcionais com trailing block match no ffmpeg (`-map 0:s?`) ou fazer o analizador (ffprobe) verificar se a stream `s` existe antes no Mux.
2. **Locking do `os.replace()` no Windows:** 
   Um arquivo possivelmente travado por scan de terceiros (ex: Plex gerando Thumbnail do recém extraído 4K) pode gerar `PermissionError` durante a substituição atômica.
   * **Decisão:** O método `replace_original` deve possuir um retry loop (esperar alguns segundos e tentar de novo em caso de `PermissionError`).
3. **Variável Hash do qBittorrent:** 
   O script usará a variável de ambiente `radarr_download_id` do evento on-import. É preciso confirmar se o Radarr preenche isso de forma confiável com o *hash* do torrent ou só o internal id no client.
   * **Ação Recomendada:** Adicionar logs defensivos que capturem e mostrem o `radarr_download_id` e fallback para cleanup manual na V2 caso não seja o hash.
4. **Cleanup das Tralhas `.eac3` temporárias:** 
   Não havia citação direta de qual módulo limpa o arquivo `audio_ptbr.eac3` ou eventuais falhas do `output_tmp.mkv`. 
   * **Decisão:** O controlador `trigger.py` deverá possuir um bloco `finally:` isolado cuidando especificamente de apagar o `.eac3` e o `output_tmp.mkv` residual sempre garantindo que disco temp fique limpo, mesmo em Exceptions de sistema.
5. **Divergência de Dependência (ffmpeg-python vs subprocess):** 
   O `requirements.txt` sugere o uso de `ffmpeg-python`, mas PRD dá exemplos complexos de bash listando mappings literais (`10.1` e `3.5`). 
   * **Decisão:** Manter-se fiel aos subcomandos de `subprocess.run` do shell será mais robusto (evitando a tradução pesada que o `ffmpeg-python` geraria de mapeamentos).

## 4. Proposta de Implementação da Fase 1 (MVP) e Justificativas

**Proposta:** *Bottom-Up (Das fundações até o CLI handler)*

1. **`config.py` e `notifier.py`**
   * *Justificativa:* Dependências de infraestrutura base (zero interdependências). Será necessário pilar configs e logs para debugar os demais.
2. **`analyzer.py` e `merger.py` (Utilitários Core de Vídeo)**
   * *Justificativa:* Isolam as chamadas subprocess do ffmpeg. Contêm a lógica core do sistema (extração/sincronia/identificação). Podem ser testadas sozinhas injetando paths hardcoded mockados.
3. **`radarr_client.py` e `qbit_client.py` (Adapters HTTP)**
   * *Justificativa:* Isolam as chamadas de rede à APIs expostas simulando payload nativo. Finalizando-os, todas as ferramentas isoladas estarão validadoras de status HTTP/arquivos locais.
4. **`trigger.py` (Maestro Entrypoint)**
   * *Justificativa:* Unifica os utilitários, lê as variáveis de ambiente base do Radarr, aplica blocos condicionais de execução limpos com tratativas de erro generalizadas (`try/except/finally`) para clean-up e saída amigável.
