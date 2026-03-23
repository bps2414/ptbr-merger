---
description: Build cinematic landing pages with preset design systems, GSAP animations, and optional Stitch integration
---

# build-site

End-to-end workflow for building a cinematic, pixel-perfect landing page from scratch.

## When to Use

- User asks to "build a site", "create a landing page", "make a one-pager"
- User wants a cinematic/premium web presence with animations
- User wants to use Stitch MCP to generate or extend pages

## Prerequisites

- Node.js installed
- Agent: `site-builder` (loaded automatically)

## Workflow Steps

### Phase 1 — Discovery (Socratic Gate)

> **DO NOT SKIP.** Ask all 4 questions before writing any code.

Activate the `site-builder` agent and present the 4 mandatory questions:

1. **Brand name + purpose** (one sentence)
2. **Aesthetic preset** (A: Organic Tech, B: Midnight Luxe, C: Brutalist Signal, D: Vapor Clinic)
3. **3 value propositions** (short phrases)
4. **Primary CTA** (what visitors should do)

Wait for user responses. Do not assume answers.

### Phase 2 — Design Token Mapping

From the user's answers:

1. Load the selected preset's full design tokens from `site-builder` agent:
   - Palette (primary, accent, background, dark)
   - Typography (heading, drama, data fonts)
   - Image mood (Unsplash keywords)
   - Hero phrase pattern

2. Generate all copy:
   - Hero headline (following preset's phrase pattern)
   - Feature card titles + descriptions (from 3 value props)
   - Philosophy contrast statements (from brand purpose)
   - Protocol steps (from brand methodology)
   - Pricing tier names (aligned to brand)

### Phase 3 — Scaffold & Build

```bash
npm create vite@latest {brand-slug} -- --template react
cd {brand-slug}
npm install gsap @gsap/react lucide-react
```

Create all files following `site-builder` agent's Component Architecture:

| Component | File | Priority |
|-----------|------|----------|
| Navbar | `App.jsx` or `components/Navbar.jsx` | P0 |
| Hero | `App.jsx` or `components/Hero.jsx` | P0 |
| Features (3 interactive cards) | `components/Features.jsx` | P0 |
| Philosophy | `components/Philosophy.jsx` | P1 |
| Protocol (sticky stack) | `components/Protocol.jsx` | P1 |
| Pricing | `components/Pricing.jsx` | P2 |
| Footer | `components/Footer.jsx` | P2 |
| Noise overlay + utilities | `index.css` | P0 |

**Rules:**
- Load Google Fonts via `<link>` in `index.html`
- Use real Unsplash URLs (match `imageMood`)
- Every animation uses `gsap.context()` with cleanup
- Mobile-first responsive design

### Phase 4 — Quality Assurance

Before declaring done, verify:

| Check | How |
|-------|-----|
| All animations work | Open dev server, scroll through all sections |
| All images load | No broken Unsplash URLs |
| Mobile responsive | Check at 375px, 768px, 1440px |
| No console errors | DevTools clean |
| CTA visible | Above fold on desktop, prominent on mobile |
| Noise overlay active | Subtle grain visible on backgrounds |

Use `verification-before-completion` skill.

### Phase 5 — Stitch Extension (Optional)

If the user wants to add more pages or extract the design system:

1. **Extract design system:** Run `design-md` skill to create `DESIGN.md` from the built site
2. **Generate new pages:** Use `enhance-prompt` to polish the prompt, then generate via Stitch MCP
3. **Convert to React:** Use `react-components` skill to convert Stitch HTML into modular components
4. **Autonomous loop:** (Normal profile+) Use `stitch-loop` for multi-page autonomous generation

## Integration Notes

- This workflow auto-routes to the `site-builder` agent
- Skills `scroll-experience` and `tailwind-patterns` are auto-loaded via the agent's frontmatter
- The `frontend-specialist` agent can handle component-level work within the built site
- For design system extraction, the `design-md` skill works independently of Stitch MCP

## Examples

**Simple:**
> "Cria uma landing page cinematográfica para minha startup"
→ Triggers build-site workflow → Socratic Gate with 4 questions → Full build

**With Stitch:**
> "Usa o Stitch pra gerar a página About baseada no design do meu site"
→ Uses `design-md` to extract tokens → `enhance-prompt` to polish → Stitch MCP to generate

**Autonomous multi-page:**
> "Constrói 5 páginas pro meu site usando Stitch em loop"
→ Uses `stitch-loop` skill (Normal profile+) for autonomous baton-passing generation
