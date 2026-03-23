# Spec: Otimização de Performance e Fast Play

**Visão Geral**
Esta track (Bug/Performance Fix) visa corrigir gargalos de carregamento (buffering infinito) em arquivos 4K pesados reproduzidos em dispositivos de hardware limitado (TVs, celulares via Jellyfin). O foco é reduzir a carga de leitura exigida dos players.

## 1. Limpeza de Streams (Stream Diet)
- **Comportamento:** Alterar a lógica do FFmpeg em `src/merger.py` para não copiar mais todas as faixas do arquivo 4K original de forma indiscriminada (`-map 0`).
- **Regra de Filtro:** Manter apenas faixas (Áudio e Legenda) cujos idiomas sejam detectados como Português (`por`), Inglês (`eng`) ou idioma original (ex: `jpn`). Todo o lixo de dezenas de outras linguagens será sumariamente descartado. Isso reduz a carga do demuxer em mais de 70% na leitura de blocos.

## 2. Otimização Estrutural do MKV (Fast Seek)
- **Comportamento:** Melhorar o comando de merge final.
- **Técnica:** 
  - Manter rigor no `-max_interleave_delta 0`.
  - A redução de streams aliada ao interleave forçado já proporciona um alívio gigante para a leitura de disco e rede, evitando lag pós-seek.

## 3. Preservação Total (Zero Encode)
- **Comportamento:** O sistema continua restrito a cópia bit a bit (`-c copy`) do vídeo e áudio. Não haverá transcoding do EAC3, o que garante a preservação do Dolby Vision (HDR) e evita uso de CPU na hora da mesclagem.