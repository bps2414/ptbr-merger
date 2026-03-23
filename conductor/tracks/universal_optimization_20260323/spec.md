# Spec: Universal Optimization Mode (Stream Diet Universal)

**Visão Geral**
Atualmente o PTBRMerger só processa arquivos 4K quando ele precisa injetar um áudio PT-BR. Esta melhoria visa aplicar as técnicas de "Stream Diet" (limpeza de faixas inúteis) e "Interleave Delta 0" em TODOS os arquivos 4K importados, mesmo que já possuam áudio em português ou que o áudio não tenha sido encontrado, garantindo a melhor experiência de playback em Smart TVs.

## 1. Comportamento Universal
- **Sempre Otimizar:** Todo arquivo 4K detectado pelo `run_analyzer` deve passar pelo processo de otimização, independentemente da presença de áudio PT-BR.
- **Limpeza de Lixo:** Remover streams de idiomas irrelevantes de todos os arquivos 4K na chegada (Import).
- **Intercalação Perfeita:** Forçar `-max_interleave_delta 0` em todos os arquivos para evitar buffering pós-seek.

## 2. Fluxo de Execução
1. **Lançamento 4K Importado:**
    - Se já tem PT-BR: Otimiza o arquivo e finaliza.
    - Se não tem PT-BR e não há candidatos: Otimiza o arquivo e finaliza.
    - Se não tem PT-BR e HÁ candidatos: Injeta o torrent no qBit. Quando o download terminar, o processo de Mux fará uma SEGUNDA otimização (injetando o áudio novo).

## 3. Segurança
- Manter o Dry-Run funcional.
- Garantir que o processo de otimização não corrompa arquivos 4K nativos.
