# Implementation Plan: Otimização de Performance e Fast Play

**Objetivo:** Refatorar o processo de muxing para remover dezenas de faixas inúteis do arquivo final, aliviando o leitor de MKV das Smart TVs e celulares, eliminando o lag extremo de navegação.

## Phase 1: Mapeamento Seletivo de Faixas (Analyzer)
- [ ] Task: Alterar `src/analyzer.py` para listar os índices das faixas (audio/subtitle) permitidas (`por`, `eng`, `jpn`, `und` - caso não haja tag).
    - [ ] Escrever/Atualizar testes para verificar o extrator de faixas baseadas em idioma.
    - [ ] Criar função auxiliar `get_allowed_streams(filepath) -> list[int]`.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Mapeamento Seletivo' (Protocol in workflow.md)

## Phase 2: Refatoração do Muxing (Merger)
- [ ] Task: Modificar a lógica do FFmpeg em `src/merger.py` (função `mux_audio`).
    - [ ] Substituir o "dump" de todas as faixas (`-map 0:a`, `-map 0:s?`) por mapeamento dinâmico e seletivo.
    - [ ] Garantir que o `-max_interleave_delta 0` permaneça.
    - [ ] Testar localmente com dry-run para validar o array de comandos.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Refatoração do Muxing' (Protocol in workflow.md)

## Phase 3: Rollout e Teste de Performance
- [ ] Task: Aplicar a correção do Mux e testar com um arquivo grande.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Rollout e Teste' (Protocol in workflow.md)