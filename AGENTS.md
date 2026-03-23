# Codex Project Integration

Este projeto usa `.agents/` como base local de conhecimento. Ao trabalhar neste repositorio, trate esses arquivos como instrucoes do projeto, sem depender de instalacao global.

## Objetivo

Integrar o conteudo de `.agents/` ao fluxo do Codex apenas neste workspace.

## Fonte de verdade

- Regras gerais: `D:/ptbr-merger/.agents/rules/AGENTS.md`
- Arquitetura do kit: `D:/ptbr-merger/.agents/ARCHITECTURE.md`
- Skills ativas: `D:/ptbr-merger/.agents/skills/*/SKILL.md`
- Workflows de referencia: `D:/ptbr-merger/.agents/workflows/*.md`
- Personas/agentes de referencia: `D:/ptbr-merger/.agents/agents/*.md`

## Como o Codex deve usar

1. Antes de executar uma tarefa, identificar se existe skill compativel em `.agents/skills/`.
2. Se houver, abrir apenas o `SKILL.md` relevante e carregar o minimo necessario.
3. Usar `scripts/` e `assets/` da skill quando existirem, em vez de recriar fluxos manualmente.
4. Tratar `workflows/` como playbooks textuais, nao como comandos nativos.
5. Tratar `agents/` como especializacoes conceituais para roteamento, nao como subagentes obrigatorios.

## Limites de compatibilidade

- O Codex neste projeto nao possui slash commands nativos como `/orchestrate` ou `/debug`.
- Arquivos em `.agents/workflows/` devem ser interpretados manualmente.
- Arquivos em `.agents/agents/` definem fronteiras e heuristicas uteis, mas nao substituem as capacidades reais do runtime atual.
- Se uma skill mencionar ferramentas indisponiveis no runtime, aplicar a melhor adaptacao local e registrar a limitacao brevemente.

## Regra de escopo

Esta integracao vale apenas para `D:/ptbr-merger` e seus arquivos. Nao copiar skills para `$CODEX_HOME`, nao instalar globalmente e nao assumir disponibilidade fora deste repositorio.

## Preferencias praticas

- Priorizar as skills locais de `.agents/skills/` antes de alternativas globais equivalentes.
- Para trabalho exploratorio, consultar primeiro `.agents/ARCHITECTURE.md` e depois a skill mais relevante.
- Para validacao apos mudancas, seguir a skill `lint-and-validate`.
- Antes de declarar conclusao, seguir a skill `verification-before-completion`.
