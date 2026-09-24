# Landscape: "Living page as unit of work" (Sept 2026)

Vision parts: **V1** doc-as-container · **V2** live embeds (HTML template bound to JSON) · **V3** terminal/process blocks · **V4** data blocks / binding · **V5** publish to own domain · **V6** agent memory as visible/editable files · **V7** agent conversation inside the doc · **V8** (constraint) fresh agent context per call.
Legend: ● strong, ◐ partial, ○ none/thin. [unverified] = single secondary source.

## A. Knowledge/doc tools adding agents + publishing

**Notion** — https://www.notion.com/product/agents · https://www.notion.com/help/notion-sites-availability-and-pricing
Custom Agents (Business/Enterprise) run on triggers and edit pages/DBs; MCP integrations. Since May 2026 Custom Agents bill on credits ($10 / 1,000), agents pause when out. Sites: free on notion.site; custom domain $10/mo per domain. Overlap: V1 ◐ (block model, not markdown), V4 ● (databases), V5 ●, V6 ◐ (agent instructions live in @-mentioned pages), V7 ◐ (sidebar). Weaknesses: agents can't call agents; credit metering opaque; no code/terminal; no local files.

**Obsidian (Bases, Canvas, Publish + agent plugins)** — https://obsidian.md/help/bases/views · https://obsidian.md/publish
Local markdown vault; Bases (.base YAML, table/cards/list/kanban/map views, formulas, embeddable via `![[File.base#View]]`) = closest thing to "declarative data view bound to files". Publish $8–10/mo per site, custom domain. Agent plugins (MIT, desktop-only): **Claudian** (embeds Claude Code/Codex/OpenCode/Pi/Grok; inline word-level diff; @mention files; skills; MCP; **2.2M downloads**); Roasbeef/obsidian-claude-code; obsidian-second-brain ("persistent memory for Claude Code + 6 CLI agents as plain markdown"); obsidian-memory-plugin. Overlap: V1 ●, V2 ○, V3 ○, V4 ◐, V5 ●, V6 ● (vault-as-memory), V7 ● via Claudian (side panel). Weaknesses: plugins desktop-only, no sandbox; chat is a side panel; Publish is static.

**Craft (+ Craft Agents)** — https://www.craft.do/pricing
Craft Agents (Jan 2026, Apache-2.0, Electron, "visual Claude Code" on Claude Agent SDK) with Sources, permission modes, parallel agents; Craft Docs used internally as the agent's memory layer. Overlap: V5 ◐, V6 ◐, V7 ○ (separate app). Weakness: two disconnected products.

**Anytype** — local-first object graph; Web Publishing (subdomain); no agent features. V4 ◐, V5 ◐.
**AFFiNE** — OSS doc+whiteboard+database; AI copilot assistant-grade; share links. V1 ◐, V4 ◐, V5 ◐, V7 ◐.
**Tana** — supertag knowledge graph + AI agents; MCP server; connectors. V4 ●, V6 ◐, V7 ◐. No domains.
**Capacities / Reflect** — minimal overlap.
**Logseq DB** — OSS, DB version iterating; publishing; agent skill. V1 ◐, V5 ◐, V6 ◐. Slow.
**SiYuan** — AGPL, ~45k★, "knowledge workspace where humans and AI agents work together"; MCP. V1 ◐, V6 ◐, V7 ◐.
**Heptabase** — in-app AI Agent (2026), MCP + CLI, "Better integration with Codex & Claude Code" in progress, Interactive Cards in progress. V4 ◐, V5 ◐, V7 ●.

## B. Computational / reactive notebooks and "docs that run"

**Observable (Notebooks 2.0 / Notebook Kit / Framework)** — https://observablehq.github.io/notebook-kit/ · https://observablehq.com/framework/
Notebooks 2.0: human-editable HTML file format; Notebook Kit builds static sites; Observable Desktop with integrated AI; Framework = markdown pages + data loaders (any language, build time) + reactive JS. Overlap: V1 ●, V2 ●, V3 ◐, V4 ●, V5 ●, V6 ○, V7 ◐.

**marimo (+ molab)** — https://marimo.io/features/feat-ai
Apache-2.0 reactive Python notebook as pure .py; deploy as app; WASM export; AI chat; `marimo pair` agent skill (Claude Code works inside live kernel); ACP-compatible agent sidebar; MCP. V1 ◐, V2 ●, V3 ●, V4 ●, V5 ◐, V6 ○, V7 ●.

**Runme** — https://runme.dev/ · https://github.com/runmedev/runme
Apache-2.0, "DevOps notebooks built with markdown": README code fences become executable cells; cell metadata in fence attributes (`{name=..., interactive=...}`); VS Code extension (145k installs), CLI, web. **V3 ● (best-in-class markdown terminal blocks)**, V1 ●, V4 ◐.

**Deepnote** — open source Apache-2.0 (2026) [unverified]; Agent Workspace; notebooks → apps. V2 ◐, V3 ●, V4 ●, V5 ◐, V7 ●.
**Hex** — https://hex.tech/blog/introducing-notebook-agent/ Notebook Agent: per-cell diff review with accept/reject, auto-version per thread, @-mention tables/cells. V3 ●, V4 ●, V5 ◐, V7 ●.
**Jupyter AI** — BSD-3; v3 native chat with ACP agents (Claude Code, Codex, Copilot, Gemini), Jupyter MCP server. V3 ●, V7 ●.
**Quarto** — .qmd markdown + executable cells, dashboards, publish anywhere; no AI. V1 ●, V2 ◐, V3 ◐, V5 ●.
**Livebook (Elixir)** — Apache-2.0, `.livemd` = markdown subset with code + outputs, Smart Cells (GUI cells that emit code), deploy as apps. V1 ●, V2 ◐, V3 ●, V4 ●, V5 ◐.
**Pluto.jl** — reactive Julia; static export. V2 ◐, V3 ◐.
**Warp Notebooks / Oz / Agent Memory** — markdown runbooks with runnable blocks; Oz cloud orchestration; Agent Memory waitlist. V3 ●, V1 ◐, V6 ◐, V7 ◐.
**Zed / VS Code** — Zed REPL runs Jupyter kernels inline; agent panel with ACP; VS Code Copilot edits .ipynb. V3 ●, V7 ◐.

## C. AI page/site builders, "chat → page → publish"

**ChatGPT Sites** — https://help.openai.com/en/articles/20001339-creating-and-managing-chatgpt-sites
Build sites/apps in Work mode; preview → deploy; bring-your-own custom domain via DNS; forms, sign-in, integrations; 10 GB DB per site + object storage; Plus/Pro/Business/Edu, not Free/Go, not EEA/UK/CH; plan-based caps; edit by reopening the creation chat. V5 ●, V4 ●, V7 ◐, V6 ○, V3 ○.

**Claude artifacts / Cowork artifacts** — https://support.claude.com/en/articles/9547008-publish-and-share-artifacts
Publish to claude.ai/artifact link (no custom domain); Cowork artifact system (Aug 2026): connect to apps/data, viewer's own connector access, per-version sharing & restore, shared DB, "ask Claude" from page. V2 ●, V4 ●, V5 ◐, V7 ◐. Weak: no domains; unpublish deletes storage.

**Google Antigravity** — Agents emit Artifacts (task lists, plans, diffs, walkthroughs, screenshots, recordings) reviewed with Google-Docs-style inline comments the agent incorporates; auto-maintained AGENTS.md. V6 ◐, V7 ◐ (very close to "outputs as pages").

**Perplexity Pages / Computer** — Pages hosted on perplexity.ai only, no export; Computer publishes to pplx.app or via Vercel connector for custom domains. V5 ◐, V7 ◐.
**Manus** — one-click publish, custom domain, Cloud Run hosting. V5 ●, V4 ◐, V7 ◐.
**Lovable** — React+Supabase; custom domain on paid; 8M+ users, $300M ARR [secondary]. V5 ●, V4 ●, V7 ◐.
**v0 (Vercel)** — shadcn/Tailwind UI generation; agentic mode; deploy to Vercel. V5 ●, V2 ◐.
**Bolt.new** — WebContainers; Netlify deploy. V3 ◐, V5 ◐.
**Framer AI** — hosted sites w/ domains; no code export. V5 ●.
**Typedream** — acquired by beehiiv (2024); not a standalone competitor.
**Val Town (Townie)** — TypeScript vals hosted instantly; HTTP/cron/email triggers; custom domains on Pro. V3 ●, V5 ●, V7 ◐.
**Replit (Agent 4)** — full IDE + terminal; deployments; custom domains. V3 ●, V5 ●, V7 ◐.
**GitHub Spark** — public preview; KV store; github.app URLs. V4 ◐, V5 ◐.
**Google Opal** — NL → visual workflow mini-apps. V5 ◐, V7 ◐.
**Gamma** — docs/decks/websites with custom domains; 70M users, $100M+ ARR. V5 ●, V2 ◐.
**Tome** — shut down April 2025 (data deleted); 20M users, <$4M ARR. Cautionary tale.

## D. Agent memory as files

**Claude Code** — https://code.claude.com/docs/en/memory
Auto memory on by default: `~/.claude/projects/<project>/memory/` with `MEMORY.md` index + one topic file per memory, plain markdown, "Saved N / Recalled N memories" UI hints, `/memory` lists & opens files; CLAUDE.md hierarchy + AGENTS.md + `@imports`. Each session starts fresh (= V8). **V6 ●** — reference implementation.

**Codex** — https://learn.chatgpt.com/docs/customization/memories
Local memories in `~/.codex/memories/`, consolidated asynchronously after chat idle, opt-in; docs say "treat as generated state". V6 ◐.

**Letta (MemGPT)** — memory blocks (labeled text blocks in context, agent self-edits; shared blocks across agents); ADE shows context window & lets humans edit blocks live. V6 ● (editable in UI, not files).
**Mem0 / OpenMemory** — vector+graph memory API; OpenMemory MCP local dashboard. V6 ◐.
**Zep / Graphiti** — bi-temporal knowledge graph. V6 ◐.
**Cognee** — ECL pipeline → graph. V6 ◐.
**Products exposing memory in editable UI**: ChatGPT "Manage memories" (list/delete), Claude.ai memory (edit summary), Cursor Memories, Notion agents (instructions as pages), Letta ADE, Agentage (one MCP endpoint, plain markdown+YAML memory shared across Claude/ChatGPT/Cursor), Warp Agent Memory (waitlist).

## E. Template + data binding for AI-generated UI

**JSON Resume** — https://jsonresume.org/themes — schema JSON + swappable themes; proven pattern.
**Vercel json-render** — https://github.com/vercel-labs/json-render — Apache-2.0, ~18k★: developer defines a Zod catalog of allowed components/props/actions → LLM emits JSON spec → renderer (React/Vue/Svelte/Solid/RN/PDF/Email/terminal); streaming partial render; actions. Closest library to V2.
**Google A2UI** — https://a2ui.org — JSONL UI messages, "Basic" catalog, renderers React/Flutter/Lit/Angular, data model + client→server sync, streaming healing of partial LLM JSON.
**CopilotKit AG-UI** — event/state protocol unifying static, declarative (A2UI) and open-ended (MCP Apps) generative UI.
**MCP Apps** (official MCP extension, Jan 2026) — https://github.com/modelcontextprotocol/ext-apps — tools declare `_meta.ui.resourceUri` → `ui://` HTML resource → host renders in sandboxed iframe with postMessage JSON-RPC; supported by Claude web/desktop, VS Code Insiders, Goose, ChatGPT; host CSS variables for theming. **Emerging standard for "HTML view inside an agent conversation".**
**OpenAI Apps SDK** — widgets = MCP servers with HTML resources; converging on MCP Apps.
**Thesys C1** — LLM emits UI spec, React renderer; hosted, paid.
**Observable Plot / Vega-Lite** — declarative JSON chart specs.
**Streamlit / Gradio** — script-to-app; not templates.

## (1) Matrix — tools × vision parts

| Tool | V1 | V2 | V3 | V4 | V5 | V6 | V7 |
|---|---|---|---|---|---|---|---|
| Notion | ◐ | ○ | ○ | ● | ● | ◐ | ◐ |
| Obsidian (+Claudian, Bases, Publish) | ● | ○ | ○ | ◐ | ● | ● | ● |
| Craft (+Agents) | ◐ | ○ | ○ | ○ | ◐ | ◐ | ○ |
| Anytype / AFFiNE / Capacities / Reflect | ◐ | ○ | ○ | ◐ | ◐ | ○ | ◐ |
| Tana | ○ | ○ | ○ | ● | ○ | ◐ | ◐ |
| Logseq DB / SiYuan | ● | ○ | ○ | ◐ | ◐ | ◐ | ◐ |
| Heptabase | ◐ | ○ | ○ | ◐ | ◐ | ○ | ● |
| Observable Framework/Notebooks 2.0 | ● | ● | ◐ | ● | ● | ○ | ◐ |
| marimo | ◐ | ● | ● | ● | ◐ | ○ | ● |
| Runme | ● | ○ | ● | ◐ | ○ | ○ | ○ |
| Deepnote / Hex | ◐ | ◐ | ● | ● | ◐ | ○ | ● |
| Jupyter AI | ◐ | ◐ | ● | ◐ | ○ | ○ | ● |
| Quarto / Livebook / Pluto | ● | ◐ | ● | ◐ | ●/◐ | ○ | ○ |
| Warp Notebooks/Oz | ◐ | ○ | ● | ○ | ○ | ◐ | ◐ |
| ChatGPT Sites | ○ | ◐ | ○ | ● | ● | ○ | ◐ |
| Claude artifacts / Cowork | ○ | ● | ○ | ● | ◐ | ○ | ◐ |
| Antigravity artifacts | ◐ | ○ | ◐ | ○ | ○ | ◐ | ◐ |
| Perplexity / Manus / Genspark | ○ | ○ | ○ | ◐ | ●/◐ | ○ | ◐ |
| Lovable / v0 / Bolt / Replit / Val Town | ○ | ◐ | ◐/● | ● | ● | ○ | ◐ |
| GitHub Spark / Opal / Gamma / Framer | ○ | ◐ | ○ | ◐ | ◐/● | ○ | ◐ |
| Claude Code auto memory | — | — | — | — | — | ● | — |
| Codex memories | — | — | — | — | — | ◐ | — |
| Letta / Mem0 / Zep / Cognee | — | — | — | — | — | ◐ | — |
| json-render / A2UI / MCP Apps / Thesys | ○ | ● | ○ | ● | ○ | ○ | ● (in chat) |
| JSON Resume / Vega-Lite | ○ | ● | ○ | ● | ◐ | ○ | ○ |

No tool covers all seven. Nearest composites: Obsidian+Claudian+Bases+Publish (missing V2/V3), Observable Framework (missing V6/V7; V3 only at build time).

## (2) Well-served vs thin

Well-served: V5 publish-to-domain (commodity); V3 terminal blocks in markdown (Runme, Livebook, marimo, Jupyter); V6 memory-as-files (Claude Code, Obsidian-vault ecosystem); V2 "LLM emits JSON, template renders" as libraries (json-render, A2UI, MCP Apps) but not inside any document product; V7 agent editing cells with review (Hex, Claudian, Antigravity).

Thin/open: agent transcript as a first-class block inside the page; live embeds that survive publishing (V2+V5) from a markdown source; data blocks in markdown bound to templates (V4+V2); stateless-per-call agents with page as the only state (V8); memory editable in the same surface as the work.

## (3) Features worth borrowing (source named)
1. Runme fence-attribute convention for terminal blocks; add `{output=persist}` (Livebook stores outputs similarly).
2. Obsidian Bases embed syntax (`![[file.base#View]]`) for view blocks bound to JSON data blocks.
3. json-render / A2UI catalog constraint: agent may only emit JSON validating against a schema catalog; stream-render partial JSON with healing.
4. MCP Apps `ui://` + sandboxed iframe + host CSS variables: make each live embed an MCP-Apps-compatible resource so the same view renders inside Claude/ChatGPT/VS Code and on the published page.
5. Hex per-cell diff + per-thread version; Antigravity inline comments the next agent call reads — comments become the prompt; no session needed.
6. Claude Code `MEMORY.md` index + topic files + "Saved/Recalled N" chips: render memory as pages, show which memory files were loaded per call.
7. Notion "instructions live in @-mentioned pages" + Craft "docs are the agent's memory": page frontmatter `agent: {model, tools, memory: [..]}` makes each page self-describing.
8. Cowork artifacts' viewer-connector access + per-version share links; ChatGPT Sites' per-site DB: publish a version, not "latest"; optional KV/SQLite per page.

Anti-patterns: credit metering that pauses agents (Notion), unpublish-once rules (Claude), no export (Perplexity Pages, Framer), platform shutdown deleting data (Tome).
