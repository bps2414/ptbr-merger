---
trigger: always_on
---

# AGENTS.md — Agent Routing & Boundary Rules

> Este arquivo define COMO rotear requests para o agente correto e suas regras de fronteira.

---

## 🔴 REGRA #1: orchestrator NÃO é default

> **orchestrator = SOMENTE quando 2+ domínios distintos precisam trabalhar juntos.**
> Se o request cabe em 1 agente → use esse agente diretamente.

---

## 🗺️ Keyword → Agent (primeira correspondência)

| Keywords no request | Agent | Skills (frontmatter) |
|---|---|---|
| component, react, ui, ux, css, tailwind, frontend, hook, state | `frontend-specialist` | nextjs-react-expert, web-design-guidelines, tailwind-patterns, frontend-design, design-md, enhance-prompt |
| landing page, site, website, hero, parallax, one-pager | `site-builder` | scroll-experience, tailwind-patterns, react-patterns, frontend-design, design-md, enhance-prompt, react-components |
| backend, server, api, endpoint, auth, express, fastapi, hono | `backend-specialist` | nodejs-best-practices, api-patterns, database-design, mcp-builder |
| schema, SQL, migration, prisma, drizzle, database design | `database-architect` | database-design |
| bug, error, crash, not working, broken, fix, investigate | `debugger` | systematic-debugging |
| test, testing, coverage, TDD, E2E, jest, vitest | `test-engineer` | testing-patterns, tdd-workflow, webapp-testing, code-review-checklist |
| mobile, iOS, Android, React Native, Flutter, Expo | `mobile-developer` | mobile-design |
| security, vulnerability, audit, OWASP | `security-auditor` | vulnerability-scanner, red-team-tactics, api-patterns |
| pentest, red team, exploit | `penetration-tester` | vulnerability-scanner, red-team-tactics, api-patterns |
| deploy, CI/CD, Docker, infrastructure, PM2 | `devops-engineer` | deployment-procedures, server-management |
| performance, speed, Web Vitals, optimize, profiling | `performance-optimizer` | performance-profiling |
| SEO, meta tags, ranking, sitemap | `seo-specialist` | seo-fundamentals, geo-fundamentals |
| plan, roadmap, task breakdown, milestones | `project-planner` | app-builder, plan-writing, brainstorming |
| requirements, user stories, backlog | `product-manager` | plan-writing, brainstorming |
| MVP, strategy, product vision | `product-owner` | plan-writing, brainstorming |
| game, unity, godot, phaser, multiplayer | `game-developer` | game-development (12 sub-skills) |
| n8n, webhook, automation, workflow automation | `automation-specialist` | n8n-mcp-tools-expert, n8n-workflow-patterns, n8n-expression-syntax, n8n-node-configuration, n8n-validation-expert |
| docs, README, documentation, manual | `documentation-writer` | documentation-templates |
| legacy code, refactor, tech debt | `code-archaeologist` | refactoring-patterns, code-review-checklist |
| codebase analysis, map, discovery, explore | `explorer-agent` | architecture, plan-writing, brainstorming, systematic-debugging |
| E2E automation, CI pipeline, QA pipeline | `qa-automation-engineer` | webapp-testing, testing-patterns, web-design-guidelines |
| coordinate, orchestrate, 2+ domains simultâneos | `orchestrator` | parallel-agents, behavioral-modes, plan-writing, brainstorming, architecture |

### Protocolo de Uso

1. **Match keywords** do request na tabela acima (primeira correspondência)
2. **Ler** `.agents/agents/{agent}.md` → carregar skills do frontmatter `skills:`
3. **Anunciar**: `🤖 **Applying knowledge of @[agent-name]...**`
4. **Carregar skills**: Ler cada SKILL.md listada no frontmatter
5. **Anunciar**: `📖 Using skill: [nome]` — para CADA skill carregada
6. **Se Agent=orchestrator** → revalidar: o request REALMENTE precisa de 2+ agentes?

---

## 🔴 Agent Boundary Enforcement

**Cada agente DEVE ficar no seu domínio. Cross-domain = VIOLAÇÃO.**

| Agent | ✅ CAN Do | ❌ CANNOT Do |
|-------|----------|-------------|
| `frontend-specialist` | Components, UI, styles, hooks | Test files, API routes, DB |
| `backend-specialist` | API, server logic, DB queries | UI components, styles |
| `test-engineer` | Test files, mocks, coverage | Production code |
| `mobile-developer` | RN/Flutter, mobile UX | Web components |
| `database-architect` | Schema, migrations, queries | UI, API logic |
| `security-auditor` | Audit, vulnerabilities | Feature code, UI |
| `devops-engineer` | CI/CD, deployment, infra | Application code |
| `debugger` | Bug fixes, root cause | New features |
| `explorer-agent` | Codebase discovery | Write operations |

### File Type Ownership

| File Pattern | Owner Agent |
|---|---|
| `**/*.test.{ts,tsx,js}`, `**/__tests__/**` | `test-engineer` |
| `**/components/**` | `frontend-specialist` |
| `**/api/**`, `**/server/**` | `backend-specialist` |
| `**/prisma/**`, `**/drizzle/**` | `database-architect` |

> Se um agente precisa escrever fora do seu domínio → INVOCAR o agente correto para aquele arquivo.
