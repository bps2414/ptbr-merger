---
description: Build n8n workflow automations with AI assistance. Activates the automation-specialist agent and n8n vault skills. Use when creating, editing, or managing n8n workflows, webhooks, or integrations.
---

# /automate — n8n Workflow Builder

$ARGUMENTS

---

## Purpose

This workflow activates **automation mode**: the `automation-specialist` agent and all n8n skills are loaded to help you design, build, and deploy n8n workflows with full AI assistance.

---

## 🚀 First Time? Setup the n8n-mcp Server

Before building workflows, the n8n-mcp MCP server must be connected. Choose your setup:

---

### Option A: VS Code + GitHub Copilot (`--vscode` mode)

**Step 1** — Create `.vscode/mcp.json` in your project:

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "n8n-mcp-token",
      "description": "Your n8n-MCP AUTH_TOKEN",
      "password": true
    }
  ],
  "servers": {
    "n8n-mcp": {
      "type": "http",
      "url": "https://n8n.your.production.url/mcp",
      "headers": {
        "Authorization": "Bearer ${input:n8n-mcp-token}"
      }
    }
  }
}
```

> 💡 Replace `https://n8n.your.production.url` with your n8n instance URL.
> For local development: use `npx n8n-mcp` in stdio mode (see Option B).

---

### Option B: Antigravity / Standard Mode (local stdio)

**Step 1** — Install n8n-mcp globally:
```bash
npm install -g n8n-mcp
```

**Step 2** — Add to your MCP config (`~/.gemini/antigravity/mcp_config.json`):
```json
{
  "mcpServers": {
    "n8n-mcp": {
      "command": "node",
      "args": [
        "C:\\Users\\<USER_NAME>\\AppData\\Roaming\\npm\\node_modules\\n8n-mcp\\dist\\mcp\\index.js"
      ],
      "env": {
        "MCP_MODE": "stdio",
        "LOG_LEVEL": "error",
        "DISABLE_CONSOLE_OUTPUT": "true",
        "N8N_API_URL": "http://localhost:5678",
        "N8N_BASE_URL": "http://localhost:5678",
        "N8N_API_KEY": "<your-n8n-api-key>"
      }
    }
  }
}
```

> 💡 Get your n8n API key: n8n UI → Settings → n8n API → Create API key.
> Replace `<USER_NAME>` with your Windows username.

**Step 3** — Reload MCP servers in your IDE and confirm `n8n-mcp` appears as connected.

---

### Option C: Hosted Service (No Setup)

Use [dashboard.n8n-mcp.com](https://dashboard.n8n-mcp.com) for instant access:
- Free tier: 100 tool calls/day
- No installation required
- Use the HTTP URL in Option A's `.vscode/mcp.json`

---

## ⚠️ Safety Warning

> **NEVER edit production workflows directly with AI!**
> Always work on a **copy** first. Export backups before changes. Test in dev before production.

---

## Building Your Automation

Once n8n-mcp is connected, describe what you want to automate:

### Examples

```
"I want to receive a webhook from Stripe and send a Slack notification"
"Every morning, fetch my GitHub issues and email me a summary"
"Sync new Postgres records to a Google Sheet every 15 minutes"
"Build an AI chatbot that can query my database and respond via webhook"
```

---

## What Happens Next

The `automation-specialist` agent will:

1. **Clarify** your trigger, data flow, and outputs (if unclear)
2. **Search templates** — check 2,700+ real workflows before building from scratch
3. **Present architecture** — show you the workflow structure for approval
4. **Build iteratively** — create and refine with MCP tools
5. **Validate everything** — check each node before activating
6. **Activate** — deploy to your n8n instance

---

## Active Skills in This Mode

| Skill | Purpose |
|-------|---------|
| `n8n-mcp-tools-expert` | MCP tool selection, nodeType formats, workflow management |
| `n8n-workflow-patterns` | Architectural patterns: webhook, API, database, AI agent, scheduled |
| `n8n-expression-syntax` | Correct `{{$json.*}}` syntax, webhook data access |
| `n8n-node-configuration` | Operation-specific field requirements |
| `n8n-validation-expert` | Interpret and fix validation errors |
| `n8n-code-javascript` | Code nodes in JavaScript |
| `n8n-code-python` | Code nodes in Python |

---

## Useful Resources

- [n8n-mcp on npm](https://www.npmjs.com/package/n8n-mcp)
- [n8n-mcp GitHub](https://github.com/czlonkowski/n8n-mcp)
- [n8n Template Library](https://n8n.io/workflows/)
- [n8n Documentation](https://docs.n8n.io/)
