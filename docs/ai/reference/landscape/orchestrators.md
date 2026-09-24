# Landscape: Multi-Agent Coding Orchestrators / "Agent Development Environments" (24 Sept 2026)

Method: official sites, GitHub READMEs, docs, HN threads and comparison round-ups (Nimbalyst, dev.to/stravukarl, parallelcode.app, clawtab.cc, augmentcode.com, andyrewlee/awesome-agent-orchestrators). Star counts as of the fetch date. **[unverified]** = single secondary source; **[secondary]** = review blogs rather than official pages.

Flags used in the matrix: (a) routes tasks between Claude and OpenAI models automatically; (b) exposes/edits the agent's memory/context as files the user can see; (c) shows per-call token/context composition; (d) treats a page/document as the unit of work; (e) publishes results as web pages/sites.

## Part 1 — Tool profiles

### 1. Orca (Stably AI) — onorca.dev
Positioning: "The Agent Development Environment (ADE) for shipping with coding agents." MIT, Electron. Free; BYO agent subscriptions. macOS/Windows/Linux + iOS/Android + headless `orca serve`. 27–30+ CLI agents. Unit: git worktree. Unique: fan one prompt across N agents and compare; Design Mode; diff annotation; GitHub/Linear/Jira → worktree; SSH; Orca CLI; account hot-swap; usage tracking. Leaves agent context alone; shows subscription usage, not per-call composition; no memory editing; no docs/publishing. 73–76k stars; YC W22. Weaknesses: Electron footprint; merge conflicts between agents unaddressed; telemetry defaults.
Sources: https://www.onorca.dev/ · https://github.com/stablyai/orca · https://www.ycombinator.com/companies/stably-ai-orca

### 2. Conductor (Melty Labs) — conductor.build
"Run Claude Code, Codex, Cursor, and OpenCode in parallel." Proprietary, YC. Free / Pro $50 / Teams $60/user / Enterprise. macOS only; cloud microVMs + multiplayer. Unit: workspace = worktree. Leaves agent alone. No docs/publishing. Claims "100k+ builders" [unverified]. Weaknesses: Mac-only; closed; limited agent list.
Sources: https://www.conductor.build/ · https://www.conductor.build/pricing · https://news.ycombinator.com/item?id=44594584

### 3. Superset — superset.sh
"Agentic IDE to orchestrate 100+ coding agents in parallel." Elastic License 2.0 (source-available). Free / Pro $15/user / Enterprise. macOS desktop; CLI beta. 11+ agents. Unit: worktree. Automations (Pro), remote hosts. Leaves agent alone. 12.3k stars. Weaknesses: ELv2; macOS-centric; stateful services across worktrees unsolved.
Sources: https://github.com/superset-sh/superset · https://superset.sh/pricing · https://news.ycombinator.com/item?id=46368739

### 4. Vibe Kanban (Bloop AI) — vibekanban.com
Kanban where each card spawns an agent in a worktree. Apache-2.0; Rust + React. Free. **Company shut down 10 Apr 2026** ("couldn't find a business model"); community-maintained; Klaviyo fork. Web app. 10 agents. 28.1k stars.
Sources: https://github.com/BloopAI/vibe-kanban · https://nimbalyst.com/blog/vibe-kanban-after-bloop-whats-next/

### 5. Crystal → Nimbalyst (stravu) — nimbalyst.com
Crystal (MIT, 3.1k stars) deprecated Feb 2026 → Nimbalyst: "visual workspace for Claude Code, Codex, OpenCode — run agents in parallel, edit their work visually in markdown, mockups, diagrams, track tasks." MIT. Free / Teams $20/user. macOS/Windows/Linux/iOS/Android. Unit: session on a kanban board, bidirectionally linked to files. Integrated markdown/mockup/Mermaid/Excalidraw editors; open storage (everything is markdown on disk in git). 1.3k stars. Weaknesses: narrower agent support; self-authored comparisons.
Sources: https://github.com/nimbalyst/nimbalyst · https://nimbalyst.com/

### 6. Claude Squad (smtg-ai)
TUI to manage multiple terminal agents in tmux windows + worktrees. AGPL-3.0, Go. 8.3k stars. No visual diff review.
Source: https://github.com/smtg-ai/claude-squad

### 7. Terragon — SHUT DOWN
Cloud background-agent orchestrator for Claude Code, Codex, Amp, Gemini. Shut down 16 Jan 2026; open-sourced snapshot (Apache-2.0, 253 stars).
Source: https://github.com/terragon-labs/terragon-oss

### 8. Sculptor (Imbue) — imbue.com/sculptor
"Build product with grounded, parallel coding agents." MIT (232 stars). Free; BYO Claude subscription. macOS Apple Silicon, Linux. Unit: workspace = worktree (containers experimental). Pairing Mode; Suggestions (flags "tests passed" without coverage, CLAUDE.md violations); skills; plugin system. Sessions persist plans/chats; does not expose memory files.
Sources: https://imbue.com/product/sculptor · https://github.com/imbue-ai/sculptor

### 9. Emdash (generalaction) — emdash.com
"Open-Source Agentic Development Environment (YC W26)." Apache-2.0. Free. macOS/Windows/Linux. 34 CLI providers. Unit: worktree with $PORT injection. Issue integrations (Linear, GitHub, Jira, GitLab, Asana…). 5.6k stars. No agent-to-agent coordination.
Source: https://github.com/generalaction/emdash

### 10. Mux → Xum (Coder) — xum.coder.com
"Desktop app for isolated, parallel agentic development." Renamed after trademark complaint. AGPL-3.0. Free; BYO API keys. Its own agent loop (not a Claude Code/Codex wrapper). Unit: workspace (Local/Worktree/SSH). Manages context itself: token-usage & cost tracking per workspace, "opportunistic compaction." 2.0k stars.
Sources: https://github.com/coder/xum · https://xum.coder.com/workspaces

### 11. Herdr — herdr.dev
"The runtime your coding agents live on" — agent-aware terminal multiplexer (tmux successor) with persistent sessions and agent-state detection. Apache-2.0; single Rust binary. Free; cloud coming. ~22 agents auto-detected. Unit: pane. Socket API + CLI so agents can spawn/prompt/wait on other agents. No file isolation; no shared memory (acknowledged). 36.9k stars; **$6M seed led by Bessemer, Sept 2026**.
Sources: https://herdr.dev/ · https://github.com/herdrdev/herdr · https://herdr.dev/blog/herdr-raised-a-seed/

### 12. OpenChamber — openchamber.dev
"Agentic Development Environment based on OpenCode." MIT; 10.4k stars. OpenCode only. Unit: session. Session Goals; multi-run comparison up to 5 models; session-level notes & todos; cron scheduling; Private Relay.
Source: https://github.com/openchamber/openchamber

### 13. Symphony (OpenAI) — github.com/openai/symphony
Open-source spec + reference impl for issue-tracker-driven Codex orchestration (27 Apr 2026). Codex only; headless daemon; "rich web UI is an explicit non-goal." WORKFLOW.md defines prompts/hooks/concurrency per ticket state.
Sources: https://openai.com/index/open-source-codex-orchestration-symphony/ · https://github.com/openai/symphony/blob/main/SPEC.md

### 14. Warp Oz / Warp Agent Platform — warp.dev/oz
"Cloud agent platform for orchestrating, observing, and scaling agent fleets." Warp client open-sourced Apr 2026; Oz proprietary. Free/$20/$200/$50/user. "Warp Agent automatically routes tasks across models to balance quality and cost" (flag a). "Agent Memory: persistent, shared memory across fleet" — waitlist (flag b partial).
Sources: https://www.warp.dev/oz · https://www.warp.dev/pricing

### 15. Cursor 3 (Agents Window, cloud agents, Router)
Editor-first; Cursor 3 (Apr 2026) adds standalone Agents Window to launch/monitor many local (worktree) and cloud agents. Proprietary; Hobby free / Pro $20 / Pro+ $60 / Ultra $200 / Teams $40. **Cursor Router (Jul 2026) classifies each request and routes to the cheapest adequate model across its pool — Teams/Enterprise only** (flag a). No per-call token composition UI. $2B ARR [secondary].
Sources: https://cursor.com/blog/router · https://cursor.com/docs/cursor-router

### 16. ChatGPT desktop app (Codex mode)
Codex macOS app (Feb 2026) merged into ChatGPT desktop (Jul 2026); Chat / Work / Codex modes. OpenAI models only. Unit: thread within a Project (built-in worktrees per thread). **Sites (Jun 2026): create, save, deploy websites/dashboards/apps hosted by OpenAI — publish via URL, co-editing, WebMCP** (flag e). "Ultra mode coordinates four agents by default." Import from Claude Code/Cowork/Cursor. Event-triggered automations.
Sources: https://openai.com/index/introducing-the-codex-app/ · https://learn.chatgpt.com/docs/app · https://learn.chatgpt.com/docs/whats-new

### 17. Claude Code desktop app + Cowork (Anthropic)
Claude Desktop is a "sessions hub" for Code sessions and Cowork. Claude only. Unit: session; each desktop session auto-creates a worktree under `.claude/worktrees/`. Dispatch (persistent assistant that spawns Code sessions), Routines, Agent Teams, Remote Control. **Flags (b) and (c): Claude Code exposes auto memory as plain markdown at `~/.claude/projects/<project>/memory/MEMORY.md` + topic files (`/memory`), and `/context` gives a live breakdown by category** — the only mainstream tool that does both, but as CLI slash commands, not a persistent panel. claude.ai artifacts publish pages (flag e partial).
Sources: https://code.claude.com/docs/en/memory · https://code.claude.com/docs/en/context-window · https://code.claude.com/docs/en/worktrees

### 18. Kiro (AWS)
Spec-driven agentic IDE; autonomous agent runs up to 10 concurrent tasks in cloud sandboxes with planner/coder/verifier sub-agents. Persistent learning memory from PR feedback — not exposed as files [unverified].
Source: https://kiro.dev/blog/introducing-kiro-autonomous-agent/

### 19. Amp (Sourcegraph)
Autonomous coding agent (CLI + VS Code) with threads, subagents, Oracle mode. **Routes by task type: Claude Opus for UI, Gemini for codegen, GPT-5 for reasoning** [secondary] (flag a). Thread sharing with public URLs (flag e partial).
Source: https://baeseokjae.github.io/posts/amp-code-review-2026/

### 20. Factory Droid
Enterprise coding agent; Missions (worker/validator with separate models). **Factory Router (Jun 2026, private preview) selects the model per session and routes across providers if an endpoint degrades** (flag a).
Source: https://factory.com/news/factory-router

### 21. Devin / Devin Desktop (Cognition)
Cloud autonomous engineer; up to 10 parallel sessions; "Managed Devins" coordinator delegates to child Devins. Windsurf rebranded Devin Desktop.
Source: https://devin.ai/pricing

### 22. Zed + ACP
Zed hosts external agents over Agent Client Protocol (Claude, Codex, OpenCode, Copilot, Cursor, Pi, Gemini CLI); Threads Sidebar runs parallel threads; ACP Registry. JetBrains Air also adopted ACP — ACP is becoming the interop layer.
Sources: https://zed.dev/docs/ai/external-agents · https://zed.dev/acp

### 23. Cline Kanban (cline/kanban)
Local web app that runs CLI agents in parallel from task cards → ephemeral worktrees. Apache-2.0; 1.3k stars.
Source: https://github.com/cline/kanban

### 24. JetBrains Air
"Orchestration layer above your existing IDE"; preview Mar 2026; agents as cards. macOS only. ACP agents. Weaknesses: slow init; no merge-conflict resolution; agents don't share learnings.
Source: https://adtmag.com/articles/2026/03/19/jetbrains-launches-air-preview-for-developers-managing-multiple-ai-agents.aspx

### 25. Google Antigravity (Agent Manager)
Separate Editor and Agent Manager windows; Artifacts (task lists, plans, walkthroughs, screenshots/MP4) with Google-Docs-style comments; `AGENTS.md` knowledge base auto-synthesised. Flag (d) partial.
Source: https://antigravity.google/

### 26. Augment Intent
"What comes after the IDE" — coordinator/implementor/verifier agents around a living spec document in Spaces (worktrees). Flag (d) partial.
Source: https://www.augmentcode.com/blog/intent-a-workspace-for-agent-orchestration

### 27. Others (brief)
| Tool | One-liner | License / stars |
|---|---|---|
| cmux (manaflow) | Ghostty-based macOS terminal with agent-attention notifications, embedded browser, socket API | GPL-3.0 + commercial; 26.4k |
| T3 Code (pingdotgg) | "Agent harness control surface" desktop/web/mobile | MIT; 15.6k |
| Paneflow | Rust/GPUI native panes; MCP bridge so agents read each other's panes | GPL-3.0 |
| Parallel Code | macOS app for 2–4 supervised agents | MIT |
| ClawTab | tmux control plane + iOS/web remote | MIT |
| Proliferate | AGPL AI IDE with self-hostable control plane | AGPL; 505 |
| Berd (Block) | Tauri desktop for Goose via ACP | Apache-2.0 |
| Gas Town | 20–30-agent swarm with merge queue | OSS |
| awesome-agent-orchestrators | Curated list of ~150 tools in this category | https://github.com/andyrewlee/awesome-agent-orchestrators |

## Part 2 — Comparison matrix

Legend: ● yes · ◐ partial · ○ no.

| Tool | OSS | Price | Agents | Unit of work | UI | (a) route | (b) mem files | (c) token view | (d) doc UoW | (e) publish | Notes/docs | Traction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Orca | MIT | Free | 27–30 CLI | worktree | desktop+mobile | ○ | ○ | ◐ (usage only) | ○ | ○ | ○ | 76k★, YC |
| Conductor | No | Free→$60/u | 4 | worktree | desktop | ○ | ○ | ○ | ○ | ○ | ○ | YC |
| Superset | ELv2 | Free→$15/u | 11+ | worktree | desktop IDE | ○ | ○ | ○ | ○ | ○ | ○ | 12.3k★ |
| Vibe Kanban | Apache (sunset) | Free | 10 | card→worktree | web | ○ | ○ | ○ | ○ | ○ | ○ | 28k★, dead |
| Nimbalyst | MIT | Free/$20 | 4 | session↔files | desktop | ○ | ◐ | ○ | ◐ | ○ | ● | 1.3k★ |
| Claude Squad | AGPL | Free | 6 | tmux+worktree | TUI | ○ | ○ | ○ | ○ | ○ | ○ | 8.3k★ |
| Sculptor | MIT | Free | Claude, Pi | worktree | desktop | ○ | ○ | ○ | ○ | ○ | ◐ | 232★ |
| Emdash | Apache | Free | 34 | worktree | desktop | ○ | ○ | ○ | ○ | ○ | ○ | 5.6k★, YC |
| Xum | AGPL | Free | own loop | workspace | desktop+web | ○ | ○ | ◐ | ○ | ○ | ○ | 2k★ |
| Herdr | Apache | Free | 22 | pane | TUI | ○ | ○ | ○ | ○ | ○ | ○ | 37k★, $6M |
| OpenChamber | MIT | Free | OpenCode | session | chat+diff | ○ | ○ | ○ | ○ | ○ | ◐ | 10k★ |
| Symphony | OSS | Free | Codex | issue | none | ○ | ○ | ○ | ○ | ○ | ◐ | OpenAI |
| Warp Oz | No | $20–200 | Claude, Codex, Warp | task | dashboard | **●** | ◐ (waitlist) | ○ | ○ | ○ | ○ | Warp |
| Cursor 3 | No | $20–200 | own | worktree/VM→PR | IDE | **●** (Teams+) | ○ | ○ | ○ | ○ | ○ | $2B ARR |
| ChatGPT desktop | No | plans | OpenAI | thread in Project | desktop | ○ | ◐ | ○ | ◐ | **●** (Sites) | ● | OpenAI |
| Claude Desktop | No | $20–200 | Claude | session | desktop | ○ | **●** (files) | **●** (`/context`) | ◐ | ◐ | ◐ | Anthropic |
| Kiro | No | tiers | own | spec/task | IDE | ○ | ◐ | ○ | ◐ | ○ | ● | AWS |
| Amp | No | PAYG | own | thread | CLI | **●** | ○ | ○ | ○ | ◐ | ○ | Sourcegraph |
| Factory Droid | No | $20–200 | own | session | CLI | **●** (preview) | ○ | ○ | ○ | ○ | ○ | Factory |
| Zed + ACP | GPL | free | ACP | thread | IDE | ○ | ○ | ○ | ○ | ○ | ○ | Zed |
| Antigravity | No | preview | Gemini/Claude | workspace | editor+manager | ○ | ◐ | ○ | ◐ | ○ | ● | Google |
| Augment Intent | No | credits | Auggie+3 | space + spec | desktop | ○ | ○ | ○ | ◐ | ○ | ● | Augment |

## Part 3 — Synthesis

Crowded: (1) worktree-per-agent desktop dashboards (Orca, Conductor, Superset, Emdash, Nimbalyst, Sculptor, Xum, cmux, T3, JetBrains Air + ~50 more); two funded entrants died. (2) Agent-aware terminal multiplexers (Herdr 37k★ funded, cmux 26k, Claude Squad). (3) Kanban-card-spawns-agent. (4) Vendor-native parallelism (Cursor, ChatGPT, Claude Desktop, Devin, Kiro, Antigravity, Zed/JetBrains via ACP) — commoditising "run N of my agent in worktrees". (5) Issue-tracker-driven headless orchestration.

Empty/thin (by flag):
- (a) Automatic Claude↔OpenAI routing exists only inside proprietary agents/platforms. No open-source ADE routes tasks between Claude Code and Codex automatically across a user's existing subscriptions.
- (b) Only Claude Code itself exposes memory as user-editable files; no third-party orchestrator provides a cross-agent memory browser/editor.
- (c) Nothing shows a per-turn "what was in the prompt" composition across agents in a GUI.
- (d) Nobody makes the page/document the container; closest are Augment Intent, Nimbalyst, Antigravity, ChatGPT Work.
- (e) Only ChatGPT Sites (OpenAI-hosted) publishes as a first-class feature; no open-source/BYO-agent ADE does.

Other observations: permissive licensing dominant (MIT/Apache) with defensive exceptions (ELv2, AGPL, GPL+commercial); ACP emerging as interop standard; mobile companions table stakes; recurring complaints: review bottleneck, stateful services across worktrees, agents not sharing learnings, rate-limit exhaustion.

Comparison sources: https://nimbalyst.com/blog/best-agent-management-tools-2026/ · https://dev.to/stravukarl/best-tools-for-managing-parallel-ai-coding-agents-in-2026-14l8 · https://parallelcode.app/blog/multi-agent-coding-tools-2026/ · https://clawtab.cc/articles/best-llm-agent-ides · https://www.augmentcode.com/tools/open-source-agent-orchestrators · https://github.com/andyrewlee/awesome-agent-orchestrators
