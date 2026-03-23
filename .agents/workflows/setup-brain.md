---
description: Analisa a stack tecnológica do repositório atual e otimiza as skills ativas e o vault do Antigravity
---

# Workflow: Setup Brain & Repository Analysis

Este workflow permite que eu (o seu agente Antigravity) faça uma varredura completa da stack do seu projeto recém-criado, leia o que já está instalado (via BPS Kit), e sugira ou automatize a transferência de skills do `vault/` para a lista de `skills/` ativas (e vice-versa). 

### Passo a Passo da Análise

> **🚨 AVISO**: Leia e execute os passos um a um.

1. **Varredura Inicial**: 
   - Use as tools do sistema (ex: `list_dir`, `view_file` ou `find_by_name`) para encontrar manifestos de dependência na raiz do projeto (`package.json`, `requirements.txt`, `Pipfile`, `docker-compose.yml`, `go.mod`, etc.).
   - Analise tecnologias, frameworks, bibliotecas e estrutura arquitetural do repositório.

2. **Leitura do VAULT_INDEX**:
   - Faça `view_file` em `./.agents/VAULT_INDEX.md` para ter o mapa completo das +1100 skills inativas do seu cérebro de desenvolvedor.

3. **Check de Ativas vs Inativas**:
   - Compare o que o repositório usa com as skills que estão na pasta local de configuração (`./.agents/skills/`).
   - Elabore uma checklist baseada no contexto:
      - *Quais skills estão no vault mas deveriam ser ativadas?* (exemplo: se há Tailwind, devo puxar `tailwind-patterns`. Se for Python, `python-pro`).
      - *Existe alguma skill ativa desnecessária?* (e.g. ativou `nextjs-best-practices` mas o projeto é em Vue).

4. **Elaborar e Apresentar a Estratégia ao Usuário (`notify_user`)**:
   - Entre em modo `notify_user` e apresente ao humano:
     - As tecnologias detectadas.
     - A lista das skills ativas atuais.
     - Recomendações sólidas de X skills a serem puxadas do `vault/` para `skills/` (para turbinar o desenvolvimento) com seus respectivos motivadores.
   - Solicite aprovação do usuário para executar as movimentações locais.

5. **Execução Automática da Otimização**:
   - Assim que o usuário aprovar, utilize tools de shell para MOVER as pastas de skills:
     - Desativar: mover de `./.agents/skills/{skill}` → `./.agents/vault/{skill}`
     - Ativar: copiar de `./.agents/vault/{skill}` → `./.agents/skills/{skill}`
   - Confirme o total final de skills ativas após os movimentos.

6. **Atualização do ARCHITECTURE.md (OBRIGATÓRIO após mover skills)**:
   - Atualize SOMENTE a tabela de skills no `ARCHITECTURE.md` para refletir quais skills estão ativas vs vault.
   - **🔴 NÃO EDITE os arquivos de regras (GEMINI.md, AGENTS.md, copilot-instructions.md, agents.instructions.md).** Esses arquivos contêm routing genérico que funciona para qualquer stack — o Intent Map e a Keyword→Agent table são universais e não devem ser alterados pelo setup-brain.

### Critérios de Sucesso
- **Precisão**: Apenas skills de altíssimo valor agregado (diretamente conectadas com a stack) serão movidas. Não encha o contexto em vão. Você foi programado para manter seu Token footprint baixo.
- O `ARCHITECTURE.md` deve refletir as skills ativas atualizadas.
- **🔴 PROIBIDO**: Editar GEMINI.md, AGENTS.md, copilot-instructions.md, ou agents.instructions.md. O routing é genérico por design.
- Encerre rodando uma mensagem informando o resultado "Cérebro Calibrado e Otimizado para este ecossistema."
