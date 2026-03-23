# Implementation Plan: Otimização de Performance e Fast Play

**Objetivo:** Refatorar o processo de muxing para remover dezenas de faixas inúteis do arquivo final, aliviando o leitor de MKV das Smart TVs e celulares, eliminando o lag extremo de navegação.

## Phase 1: Mapeamento Seletivo de Faixas (Analyzer) [checkpoint: 0bcf607]
- [x] Task: Alterar `src/analyzer.py` para listar os índices das faixas (audio/subtitle) permitidas (`por`, `eng`, `jpn`, `und` - caso não haja tag). [40ce247]
    - [x] Escrever/Atualizar testes para verificar o extrator de faixas baseadas em idioma.
    - [x] Criar função auxiliar `get_allowed_streams(filepath) -> list[int]`.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Mapeamento Seletivo' (Protocol in workflow.md)

## Phase 2: Refatoração do Muxing (Merger) [checkpoint: 09529f8]
- [x] Task: Modificar a lógica do FFmpeg em `src/merger.py` (função `mux_audio`). [840c5d1]
    - [x] Substituir o "dump" de todas as faixas (`-map 0:a`, `-map 0:s?`) por mapeamento dinâmico e seletivo.
    - [x] Garantir que o `-max_interleave_delta 0` permaneça.
    - [x] Testar localmente com dry-run para validar o array de comandos.
- [x] Task: Conductor - User Manual Verification 'Phase 2: Refatoração do Muxing' (Protocol in workflow.md)

## Phase 3: Rollout e Teste de Performance [checkpoint: f2ea51e]
- [x] Task: Aplicar a correção do Mux e testar com um arquivo grande. [0a6dd44]
- [x] Task: Conductor - User Manual Verification 'Phase 3: Rollout e Teste' (Protocol in workflow.md)

## Phase: Review Fixes
- [x] Task: Apply review suggestions [abd00fb]