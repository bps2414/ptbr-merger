# PTBRMerger

O PTBRMerger é um middleware auxiliar nativo projetado para interceptar imports 4K diretos no **Radarr**, buscar automaticamente fontes 1080p DUAL ÁUDIO, extrair o canal português localmente com `FFmpeg` e mixar as trilhas num aquivo limpo livre de quebras para seu Mediacenter.

## Requisitos
- **Python 3.11+**
- **FFmpeg & FFprobe** nativos presentes nas varíaveis de ambiente (`PATH`) do Server/Host
- **Radarr (V3/V4)**
- **qBittorrent (API v2)**

---

## 1. Instalação

Abra o diretório onde você clonou o script e instale os requerimentos globais obrigatórios minimalistas em seu ambiente virtual:

```bash
pip install -r requirements.txt
```

*(O PTBRMerger não depende de `ffmpeg-python`, utilizando wrappers diretos no `subprocess` para eficiência nativa).*

---

## 2. Configurando as Variáveis (`config.yml`)

Na raiz do projeto (onde está o README), crie um arquivo chamado `config.yml`. Use o template abaixo preenchendo as informações sobre onde seus arrs estão hospedados:

```yaml
radarr:
  url: http://localhost:7878
  api_key: SUA_API_KEY_GERADA_NO_RADARR
  ptbrmerger_profile_name: PTBRMerger
  ptbrmerger_root_folder: D:\data\temp\ptbrmerger
  ptbrmerger_tag_name: ptbrmerger
  timeout: 10

qbittorrent:
  url: http://localhost:8080
  username: admin
  password: adminadmin

ffmpeg:
  ffmpeg_path: ffmpeg
  ffprobe_path: ffprobe

sync:
  max_duration_diff_seconds: 5

notifications:
  discord_webhook_url: ""  # Deixe vazio para não acionar notificações no Discord

logging:
  level: INFO
  file: ptbrmerger.log
```

---

## 3. Registrar o Script Custom no Radarr

O PTBRMerger atua como um injetor no evento final de Download. Para escutá-lo:

1. No Radarr, clique em **Settings > Connect > + > Custom Script**.
2. Configure **exatamente** da seguinte maneira:
   - **Name:** `PTBRMerger`
   - **On Import:** ✅ 
   - **On Upgrade:** ✅ 
   - *(Deixe as demais opções de evento desativadas)*
   - **Tags:** *(Vazio, pois ele rodará validando todos os filmes por padrão)*
   - **Path:** `python` *(Ou insira o caminho completo ex: `C:\Python311\python.exe`)*
   - **Arguments:** `D:\Caminho\Absoluto\Para\O\Projeto\ptbr-merger\src\trigger.py`

Clique em **Test** para rodar um health check nulo. Se retornar sucesso (checkmark verde), salve as configurações.

---

## 4. Testando a Pipeling com Modos de Segurança (Dry-Run)

Deseja atestar se o script encontra tracks e se as APIs estão lendo corretamente sem aplicar modificações invasivas de Mixagem ou Deledar mídias originais?
O script possui um switch de `--dry-run` nativo para simulação!

Trigerre diretamente via CMD:
```bash
python src/trigger.py --file-path "D:\Downloads\O-Filme-Teste-4k.mkv" --dry-run
```

Ou ligue o Dry-Run globalmente injetando Variáveis no Launcher do Radarr Server:
```powershell
set PTBRMERGER_DRY_RUN=true
```

Em DRY-RUN, a interface emitirá todo o plano de MUX de Tracks em seu `ptbrmerger.log` mas vai intencionalmente pular a gravação em disco ou remoção no qBittorrent, sendo à prova de desastres de avaliação de infraestrutura em fases prematuras.
