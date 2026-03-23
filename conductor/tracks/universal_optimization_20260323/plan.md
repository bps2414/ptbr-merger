# Implementation Plan: Universal Optimization Mode

**Objetivo:** Modificar o PTBRMerger para que ele otimize TODOS os arquivos 4K (removendo streams de áudio/legenda inúteis e forçando o interleave delta 0), mesmo que o áudio PT-BR não tenha sido encontrado ou já exista.

## Phase 1: Refatoração do Merger para Otimização Sem Injeção
- [ ] Task: Alterar `src/merger.py` (função `mux_audio`) para aceitar `audio_ptbr=None`.
    - [ ] Se `audio_ptbr` for `None`, o comando FFmpeg deve ter apenas UM `-i` (o 4K original).
    - [ ] Manter o mapeamento seletivo das faixas e o `-max_interleave_delta 0`.
- [ ] Task: Escrever testes unitários para o `mux_audio` em modo "Optimize Only".

## Phase 2: Refatoração do Fluxo de Trigger
- [ ] Task: Alterar `src/trigger.py` para sempre chamar a otimização no `run_analyzer`.
    - [ ] Se o filme já tem PT-BR, chama a otimização e notifica sucesso (ou nova tag "OPTIMIZED").
    - [ ] Se o filme não tem PT-BR e não há candidatos, chama a otimização.
    - [ ] Garantir que o `run_merger` (Bypass Mode) continue funcionando normalmente.

## Phase 3: Validação e Teste de Performance Universal
- [ ] Task: Testar com Dry-Run para verificar se o comando FFmpeg gerado está correto para ambos os casos.
- [ ] Task: Verificar se o arquivo 4K original é preservado corretamente (Zero Encode).
