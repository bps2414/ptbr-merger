# Plano do dia — PTBRMerger

**Data:** 23/03/2026  
**Objetivo:** Fechar Fase 1, resolver Samsung, organizar projeto

---

## Ordem de execução

### 1. Git — 5 minutos (faz PRIMEIRO antes de qualquer coisa)

Se o Gemini Flash quebrar algo de novo, você perde tudo de novo.

```powershell
cd D:\ptbr-merger
git init
git add .
git commit -m "Fase 1 MVP - scoring multicamada PT-BR funcional"
```

Depois de cada sessão de trabalho:
```powershell
git add .
git commit -m "descrição do que mudou"
```

---

### 2. Investigar Samsung — 15 minutos

**Hipótese principal:** o problema não é DV nem o perfil HD — é bitrate alto demais pra rede WiFi da TV ou o app Jellyfin desatualizado.

**Testes em ordem:**

**Teste A — Arquivo simples:**
Pega qualquer filme 1080p já na biblioteca e tenta abrir na Samsung. Se abrir rápido → o problema é específico do 4K pesado. Se também demorar → é o app ou a rede.

**Teste B — Verificar o que está acontecendo:**
Durante a reprodução na Samsung → abre o Jellyfin no PC → Dashboard → Active Streams. Mostra se está em `Direct Play` ou `Transcoding`. Cola o resultado aqui.

**Teste C — Atualizar o app:**
Samsung → loja de apps → Jellyfin → verifica se tem atualização disponível.

**Teste D — Bitrate máximo:**
No app Jellyfin da Samsung → Settings → Max streaming bitrate → coloca `Original` ou `80 Mbps`.

**O que esperar:**
- Samsung 2023-2024 suporta HEVC, DV e HDR10+ nativamente
- O Chainsaw Man é 2160p MA WEB-DL ~20GB — bitrate alto mas deveria rodar em Direct Play
- Se estiver transcodificando → ativa aceleração de hardware no Jellyfin

---

### 3. Fechar Fase 1 do PTBRMerger — 30 minutos

**Objetivo:** fazer o ffmpeg rodar de verdade num mux completo.

**Opção A — Testa com threshold 20s no Chainsaw Man:**
O config.yml já está com 20s. Roda o trigger real:

```powershell
cd D:\ptbr-merger
$env:radarr_eventtype="Download"
$env:radarr_movie_tmdbid="1218925"
$env:radarr_movie_title="Chainsaw Man The Movie Reze Arc"
$env:radarr_movie_year="2025"
$env:radarr_movie_tags=""
python src\trigger.py --file-path "D:\data\media\movies\Chainsaw Man The Movie Reze Arc (2025) [imdbid-tt30472557]\Chainsaw.Man.The.Movie.Reze.Arc.2025.REPACK.2160p.MA.WEB-DL.DUAL.DDP5.1.Atmos.DV.HDR10P.H.265-BYNDR.mkv"
```

Acompanha o log:
```powershell
Get-Content D:\ptbr-merger\ptbrmerger.log -Wait
```

**O que esperar se funcionar:**
```
INFO | validate_sync... OK (diferença < 20s)
INFO | get_ptbr_stream_index... encontrou stream PT-BR
INFO | extract_audio... concluído
INFO | mux_audio... concluído
INFO | replace_original... concluído
INFO | SUCCESS ✅
```

**Opção B — Se Chainsaw Man continuar falhando:**
Adiciona outro filme no Radarr sem REPACK no nome. Opções:
- Divertida Mente 2
- Deadpool & Wolverine
- Alien: Romulus

**Após mux bem-sucedido:**
1. Abre o arquivo 4K no VLC e verifica as faixas de áudio — deve ter PT-BR como primeira faixa
2. Roda ffprobe pra confirmar:
```powershell
& "C:\Users\Administrator\AppData\Local\Microsoft\WinGet\Links\ffprobe.exe" -v quiet -print_format json -show_streams "caminho\do\arquivo.mkv" | python -c "import sys,json; streams=[s for s in json.load(sys.stdin)['streams'] if s.get('codec_type')=='audio']; [print(s.get('index'), s.get('tags',{}).get('language','?'), s.get('tags',{}).get('title','?')) for s in streams]"
```
Deve mostrar:
```
1 por Português (Brasil)
2 jpn ?
3 eng ?
```

---

### 4. Refinar perfil HD — 10 minutos

**Só faz isso DEPOIS de investigar a Samsung.**

Se o problema for DV causando lentidão na Samsung:

Radarr → Settings → Profiles → HD → ajusta:

| Custom Format | Score atual | Novo score |
|---|---|---|
| DV Boost | atual | 0 ou -2000 |
| DV (Disk) | +2500 | 0 ou -2000 |
| HDR10+ Boost | +2000 | manter |
| HDR | +1500 | manter |

Assim o Radarr prefere HDR10+ sobre DV quando disponível, mas ainda baixa DV se for a única opção boa.

**Se o problema NÃO for DV:** não mexe em nada.

---

## Checklist do dia

- [ ] Git inicializado com commit inicial
- [ ] Teste A Samsung (1080p simples)
- [ ] Teste B Samsung (Direct Play vs Transcoding)
- [ ] ffmpeg rodou de verdade e mux concluído
- [ ] ffprobe confirmou faixa PT-BR no arquivo final
- [ ] Perfil HD ajustado se necessário
- [ ] Fase 1 oficialmente fechada ✅

---

## Se sobrar tempo — início Fase 2

- [ ] Verificação pós-mux implementada
- [ ] Discord embed rico implementado
- [ ] Fila persistente em JSON

---

## Ordem de prioridade se o tempo apertar

1. Git ← não negociável
2. Fechar Fase 1 (ffmpeg)
3. Samsung
4. Perfil HD
