# Spec: Fase 2 - Robustez e Integridade

**Visão Geral**
Esta track visa transformar o PTBRMerger de um MVP funcional em um sistema resiliente para produção. Focaremos em garantir que o sistema recupere-se de falhas, valide o sucesso do processamento antes de ações destrutivas (deleção de originais), e melhore a comunicação com o usuário via Discord.

## 1. Persistência de Estado (Queue Manager)
- **Arquivo:** `src/queue_manager.py` (Novo)
- **Persistência:** `queue.json` na raiz ou conforme config.
- **Campos:** `tmdbId`, `attempts`, `status` (PENDING, PROCESSING, ABANDONED), `timestamp`.
- **Comportamento:** Processamento estritamente **sequencial**. Ao iniciar, o `trigger.py` deve carregar a fila e processar itens `PENDING`.

## 2. Safety Net Pós-Mux
- **Local:** `src/merger.py` (Função `replace_original`).
- **Lógica:** Antes de `os.replace`, rodar `ffprobe` no arquivo temporário.
- **Validação:** 
    - Deve possuir stream `a:language=por`.
    - Duração deve bater com o original (tolerância 30s).
- **Fallback:** Se falhar, NÃO deletar o original, logar erro crítico e notificar.

## 3. Decorador de Retry (Exponential Backoff)
- **Local:** `src/radarr_client.py` (Aplicar em métodos de rede).
- **Algoritmo:** Customizado (Zero dependências externas), 1s, 2s, 4s, 8s max.
- **Objetivo:** Curar timeouts intermitentes em chamadas à API do Radarr/Prowlarr.

## 4. Discord Rich Embeds & Dynamic Update
- **Local:** `src/notifier.py`.
- **Funcionalidade:** Armazenar `message_id` para editar a mesma mensagem via PATCH.
- **Embed:** Thumbnail via Radarr API, barra de progresso textual, status detalhado.

## Requisitos Não-Funcionais
- **TDD:** Cobertura de testes unitários para o decorador de retry e lógica da fila.
- **Clean Code:** Manter modularidade e responsabilidade única.

## Critérios de Aceite
- Ao fechar o script durante o download e reiniciar, o processo deve ser retomado.
- O arquivo original (4K) só pode ser deletado se o validador pós-mux passar.
- Atrasos de rede no Radarr não devem quebrar o fluxo (retry automático).
- Uma única mensagem no Discord deve ser atualizada até o final do processo.
