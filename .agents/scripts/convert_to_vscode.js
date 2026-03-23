const fs = require('fs-extra');
const path = require('path');
const chalk = require('chalk');

/**
 * Converte toda a estrutura .agents importada para .github estrutural do Copilot
 * @param {string} destAgents O diretorio destino onde a copy crua (.agents) aportou
 * @param {string} destBase A raiz do repositorio final
 */
async function convertToVsCode(destAgents, destBase) {
    const gitHubDir = path.join(destBase, '.github');
    const instructionsDir = path.join(gitHubDir, 'instructions');

    console.log(chalk.dim('   [VS Code] Convertendo arquivos para sintaxe do Copilot...'));

    // Garantir que os diretórios .github e .github/instructions existem antes de qualquer escrita
    await fs.ensureDir(gitHubDir);
    await fs.ensureDir(instructionsDir);

    // Helper: aplica os path replacements padrão de .agents/ → Copilot
    function applyPathReplacements(content) {
        content = content.replace(/\.?\/?\.agents\/skills\//g, '.github/skills/');
        content = content.replace(/\.?\/?\.agents\/vault\//g, '.copilot-vault/');
        content = content.replace(/\.?\/?\.agents\/rules\/GEMINI\.md/g, '.github/copilot-instructions.md');
        content = content.replace(/\.?\/?\.agents\/rules\/AGENTS\.md/g, '.github/instructions/agents.instructions.md');
        content = content.replace(/\.?\/?\.agents\/VAULT_INDEX\.md/g, '.github/VAULT_INDEX.md');
        content = content.replace(/\.?\/?\.agents\/ARCHITECTURE\.md/g, '.github/ARCHITECTURE.md');
        content = content.replace(/\.?\/?\.agents\/agents\//g, '.github/agents/');
        content = content.replace(/\.?\/?\.agents\/scripts\//g, '.github/scripts/');
        return content;
    }

    // 1. Converter a rule master GEMINI.md em .github/copilot-instructions.md
    const geminiPath = path.join(destAgents, 'rules', 'GEMINI.md');
    if (await fs.pathExists(geminiPath)) {
        let content = await fs.readFile(geminiPath, 'utf8');
        content = applyPathReplacements(content);

        // Remover frontmatter — copilot-instructions.md não usa frontmatter
        content = content.replace(/^---[\s\S]*?---\n?/, '');

        content += `\n\n## 🔄 Workflows Base\nAs workflows antigas de Cursor (/brainstorm, etc) agora devem ser invocadas naturalmente no chat: "Rode o fluxo de brainstorm". Consulte o diretório .github/prompts/ para contexto.\n`;

        await fs.writeFile(path.join(gitHubDir, 'copilot-instructions.md'), content);
    }

    // 1.1 Converter AGENTS.md (routing rules) em .github/instructions/agents.instructions.md
    const agentsMdPath = path.join(destAgents, 'rules', 'AGENTS.md');
    if (await fs.pathExists(agentsMdPath)) {
        let content = await fs.readFile(agentsMdPath, 'utf8');
        content = applyPathReplacements(content);
        content = content.replace(/trigger:\s*always_on/g, 'applyTo: "**"');
        content = content.replace(/^---[\s\S]*?---/, `---\napplyTo: "**"\n---`);
        await fs.writeFile(path.join(instructionsDir, 'agents.instructions.md'), content);
    }

    // 2. Mover as skills ativas inteiras para .github/skills/
    const skillsDest = path.join(destAgents, 'skills');
    const copilotSkillsDir = path.join(gitHubDir, 'skills');
    if (await fs.pathExists(skillsDest)) {
        await fs.move(skillsDest, copilotSkillsDir, { overwrite: true });
    }

    // 3. Converter o Vault Index
    const vaultIndexSrc = path.join(destAgents, 'VAULT_INDEX.md');
    if (await fs.pathExists(vaultIndexSrc)) {
        let content = await fs.readFile(vaultIndexSrc, 'utf8');
        content = content.replace(/\.?\/?\.agents\/vault\//g, '.copilot-vault/');
        await fs.writeFile(path.join(gitHubDir, 'VAULT_INDEX.md'), content);
    }

    // 4. Mover o Vault inteiro para .copilot-vault/
    const vaultSrc = path.join(destAgents, 'vault');
    const copilotVaultDir = path.join(destBase, '.copilot-vault');
    if (await fs.pathExists(vaultSrc)) {
        await fs.move(vaultSrc, copilotVaultDir, { overwrite: true });
    }

    // 5. Mover as personas (AGENTS) para .github/agents/ como .agent.md
    const agentsSrc = path.join(destAgents, 'agents');
    const copilotAgentsDir = path.join(gitHubDir, 'agents');
    if (await fs.pathExists(agentsSrc)) {
        await fs.ensureDir(copilotAgentsDir);
        const agentFiles = await fs.readdir(agentsSrc);
        for (const agent of agentFiles) {
            if (agent.endsWith('.md')) {
                const content = await fs.readFile(path.join(agentsSrc, agent), 'utf8');
                const agentName = agent.replace('.md', '');
                const vsCodeAgentContent = `---\ndescription: 'Agente especializado: ${agentName}. Use para tarefas relacionadas a esse domínio.'\ntools: []\n---\n${content}`;
                await fs.writeFile(path.join(copilotAgentsDir, `${agentName}.agent.md`), vsCodeAgentContent);
            }
        }
    }

    // 6. Converter Workflows em Copilot Prompts (.github/prompts/)
    const workflowsSrc = path.join(destAgents, 'workflows');
    const copilotPromptsDir = path.join(gitHubDir, 'prompts');
    if (await fs.pathExists(workflowsSrc)) {
        await fs.ensureDir(copilotPromptsDir);
        const workflowFiles = await fs.readdir(workflowsSrc);
        for (const workflow of workflowFiles) {
            if (workflow.endsWith('.md')) {
                let content = await fs.readFile(path.join(workflowsSrc, workflow), 'utf8');
                const promptName = workflow.replace('.md', '');
                content = applyPathReplacements(content);
                content = content.replace(/\.?\/?\.agents\//g, '.github/');
                content = content.replace(/GEMINI\.md/g, 'copilot-instructions.md');
                const vsCodePromptContent = `---\nagent: agent\n---\n${content}`;
                await fs.writeFile(path.join(copilotPromptsDir, `${promptName}.prompt.md`), vsCodePromptContent);
            }
        }
    }

    // 7. Copiar ARCHITECTURE.md para .github/
    const archSrc = path.join(destAgents, 'ARCHITECTURE.md');
    if (await fs.pathExists(archSrc)) {
        let archContent = await fs.readFile(archSrc, 'utf8');
        archContent = applyPathReplacements(archContent);
        archContent = archContent.replace(/\.?\/?\.agents\//g, '.github/');
        await fs.writeFile(path.join(gitHubDir, 'ARCHITECTURE.md'), archContent);
    }

    // 8. Mover scripts de validação para .github/scripts/
    // e atualizar paths internos de .agents/skills/ → .github/skills/
    const scriptsSrc = path.join(destAgents, 'scripts');
    const scriptsDestDir = path.join(gitHubDir, 'scripts');
    if (await fs.pathExists(scriptsSrc)) {
        await fs.move(scriptsSrc, scriptsDestDir, { overwrite: true });
        const pyFiles = (await fs.readdir(scriptsDestDir)).filter(f => f.endsWith('.py'));
        for (const pyFile of pyFiles) {
            const pyPath = path.join(scriptsDestDir, pyFile);
            let pyContent = await fs.readFile(pyPath, 'utf8');
            pyContent = pyContent.replace(/\.agents\/skills\//g, '.github/skills/');
            await fs.writeFile(pyPath, pyContent);
        }
    }

    // Limpeza: remover a pasta .agents/ já migrada
    await fs.remove(destAgents);
}

module.exports = { convertToVsCode };
