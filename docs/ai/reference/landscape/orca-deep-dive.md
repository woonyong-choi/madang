# Orca (onorca.dev) — Deep-Dive Research Report

Research date: 2026-09-24. Sources are the official site/docs, the GitHub repo (raw files; star/contributor figures come from the site, star-history.com and third-party mirrors), HN threads, GitHub issues, and third-party reviews. Items marked **[UNVERIFIED]** could not be confirmed from a primary source.

## 1. Identity, company, launch, traction

| Fact | Value | Source |
|---|---|---|
| Product | Orca — "The Agent Development Environment (ADE) for shipping with coding agents"; tagline "Ship 100x with the agent IDE" | https://www.onorca.dev/ |
| Company | Stably AI (Orca), YC W22, founded 2022, San Francisco, ~25 employees. Founders: Jinjing Liang (CEO, ex-Google Chrome testing infra), Neil Parker (CTO, ex-Uber Safety ML). Company originally an AI testing product; Orca is a later product. | https://www.ycombinator.com/companies/stably-ai-orca |
| Repo | github.com/stablyai/orca, MIT license, TypeScript | https://github.com/stablyai/orca |
| Repo created / first commit | March 17, 2026 | https://www.star-history.com/stablyai/orca/ |
| Stars | 76.3k–76.6k (Sept 24 2026); ~5k forks; 387 contributors; ~+6.4k stars/week. Growth: 24k (June), 27.4k (July), 43k, 53k (late Aug), 60k (early Sept). | star-history.com; onorca.dev landing |
| Open issues / PRs | ~3,000 open issues, ~3,300 PRs, 11,406 commits on main | https://github.com/stablyai/orca |
| Version cadence | v1.4.207 on Sept 22 2026; ~740+ GitHub releases; RC/perf prerelease channels; "48–72 hours for a landed PR to be released" | https://www.onorca.dev/changelog |
| Pricing | "Free and open source. New features shipped every day." Enterprise page has no pricing tiers, only "Talk to us". | https://www.onorca.dev/enterprise |
| Platforms | macOS (DMG, Homebrew cask), Windows (.exe), Linux (AppImage, .deb, .rpm, AUR; CLI named `orca-ide` on Linux), iOS App Store, Android APK from GitHub releases | https://www.onorca.dev/docs/install |
| Launch on HN/Product Hunt | [UNVERIFIED] — no "Show HN" or Product Hunt launch page found. |

## 2. Architecture / tech stack

Source: package.json, AGENTS.md in the repo, docs.

- Electron 43 desktop app (not Tauri/Rust). Three process tiers: main / renderer / preload IPC bridge. electron-vite, Vite 7, electron-builder, electron-updater.
- Frontend: React 19.2, TypeScript 7, TailwindCSS 4, Radix UI + shadcn primitives, Lucide icons, Zustand 5 for state, Monaco 0.55 for the editor, Tiptap 3.22 for the rich markdown editor. Design tokens in main.css; lint gate rejects new color/font/shadow values.
- Terminal: xterm.js 6.1 beta with addons webgl, fit, search, serialize (scrollback persistence), ligatures, web-links; node-pty. Advertises the kitty keyboard protocol so Shift+Enter/Ctrl+Enter reach TUIs. Marketing calls it "Ghostty-class" (it is not Ghostty).
- PTY daemon: "A background daemon owns the PTYs, so closing the app window doesn't kill Claude Code, Codex, or any other agent CLI mid-task." Relaunch does a "warm-reattach". (docs/model/session-restore)
- Embedded browser: Electron WebContentsView ("a real Chromium window per worktree"); viewport emulation via Chrome DevTools Protocol; agent automation via `agent-browser` npm package; storage partitions per browser profile.
- Agent state detection: "terminal's OSC title sequence and agent hooks, which Claude Code, Codex, and several other agents emit." A hook server in Orca is the "single canonical store" for agent status; sidebar, `worktree ps`, mobile and dashboard all subscribe to it. Hook endpoints are written to disk and re-sourced on every hook invocation so sessions survive app restarts. Toggle: Settings → Agents → Agent status hooks; CLI `orca agent hooks on|off|status`. (docs/model/agents-sessions, docs/agents/hooks-memory)
- Remote: ssh2 for SSH worktrees; remote Orca runtime (`orca serve`) with a wire protocol using capability negotiation; Tailscale recommended.
- Repo layout: /src (app), /mobile (iOS/Android), /native, /cloud (mobile relay service), /skills & /skill-stubs, /tests, /docs. Tests: Vitest, Playwright (CDP). Tooling: pnpm, oxlint, oxfmt. Benchmarks: bench:idle-cpu, bench:startup.
- Telemetry: PostHog Cloud (US), anonymous random ID, on by default; disable via Settings → Privacy, `DO_NOT_TRACK=1`, or `ORCA_TELEMETRY_DISABLED=1`. (docs/telemetry)

## 3. UI inventory

### 3.1 Agent state indicators
Source: docs/model/agents-sessions, docs/terminal, docs/notifications, docs/ssh

Shared glyph vocabulary used on both agent tab titles and worktree sidebar rows:
- Spinner — actively working
- Amber question mark — awaiting user input or permission ("Needs You")
- Emerald check / dot — completed (or quietly active)
- Red dot — blocked, interrupted, or failed
- Gray dot — idle
- No indicator — plain shell / unrecognized agent

Other state surfaces:
- Terminal tab titles show agent identity + live state: working / waiting for input / completed / completed-but-unread. For Claude/Codex, the title can be the "AI Vault conversation name".
- Sidebar: unread worktrees are bolded, not badged; status bar shows agent activity inline.
- On agent exit a "Restart chip" appears in the pane; one click rehydrates same agent, same cwd.
- Agent-finished notification when an agent goes working→idle: system notification, sound, and a chip on the worktree. Custom sound per category, volume control; can be reduced to chip-only. macOS Dock badge mirrors the unread count. Header bell shows unread notifications across worktrees; clicking jumps to the worktree+pane; right-click to mark unread.
- SSH worktrees carry a chip with live SSH status: green connected, yellow reconnecting, red disconnected. Failed GitHub Actions show as a red chip on the worktree with inline job logs.
- Agent Dashboard (experimental): kanban with columns Needs You (amber-tinted cards), Working (neutral), Done (green-tinted), Idle (hidden by default; ~30 min without completion). Card header: agent icon, session conversation name, state glyph; footer: project icon, worktree name, age.
- Agents feed (Activity page, "Slack-style worktree feed"): threaded feed of agent completions, blocking states, response previews, worktree creation events; running agents pinned at top; unread badge on sidebar entry; click jumps to pane. (docs/activity)
- Native Chat shows a pulsing "Thinking" state and live tool progress.

### 3.2 Worktree / task sidebar
Source: docs/model/worktrees, docs/cli/worktree-checkpoints, docs/review/github, changelog

- Grouped by project rows (top level, with a repo icon / emoji picker) expanding into worktrees; sidebar header has its own filter input; worktrees can be pinned to top; repo rows drag-reorderable; child worktrees nest under parents; subagents appear as indented child rows under a worktree; "sleeping" (hibernated) worktrees can be hidden.
- Row content: worktree name (supports emoji shortcodes; default names are "custom prefix or marine creatures"), branch name, linked issue/PR from GitHub/Linear/Jira/GitLab, agent/terminal type, state glyph, bold-when-unread, free-text comment field ("status snapshot") settable by agents via `orca worktree set --comment`, and a workspace status (`todo | in-progress | in-review | completed | custom`). A progress row with live setup status appears during background `git fetch`/`worktree add`. Hover shows provenance ("Orca CLI" for CLI-created).
- PR-related: Stack #N map shows position in stack, stack size, base branch with status indicators; red chip for failed checks; source-control panel shows `branch → base` and review status; overflow menu: copy review link, close, reopen, Mark ready for review, Enable auto-merge.
- Diff counts per row: NOT documented. [UNVERIFIED]
- Actions: right-click → Archive/Delete; multi-select; "Delete with Descendants…"; double-click title to rename inline; Resource Manager → "Clean up workspaces" lists status, recent activity, size, git state.
- Create Worktree dialog: task name, start-from picker, optional issue link, Advanced drawer for custom branch name, project location, setup hooks, parent worktree selection.
- Right sidebar panels: Agent Session History, Ports tab (SSH port forwarding).

### 3.3 Terminal panes
Source: docs/terminal, docs/model/tabs-panes-splits

- Model: tabs live in tab groups; panes split into nested layouts; each tab holds one thing (terminal, editor, browser, diff, PR). Active-tab color bar marks focused pane. Drag tab to right edge → left/right split, bottom edge → top/bottom split; splits nest arbitrarily. Pane boundaries saved per worktree; switching worktrees swaps the entire pane tree.
- Shortcuts (remappable): New terminal Cmd-T; new agent tab Cmd-Alt-T; close Cmd-W; split right Cmd-\; split down Cmd-Shift-\; find in scrollback Cmd-F; next/prev tab Cmd-Shift-]/[; recent tab Ctrl-Tab; floating terminal Cmd+Option+A.
- Scrollback: persisted across restarts including output produced while Orca was closed (daemon); right-click "Copy context" copies a bounded transcript; "Copy Session ID".
- Themes library, contrast modes, Ghostty config import on first launch, Warp YAML theme import, OSC 52 clipboard writes allowed by default, default shell picker.
- Floating terminal / Floating Workspace: global overlay surface toggled by chord, edge button, or status bar.
- Quick Commands: saved commands or agent-prompt presets, Global or Project scoped, run from tab bar/context menu.
- Agent launch: an agent combobox in each new terminal; Orca pre-applies autonomy flags; global toggle Yolo/Manual in Settings → Agents.
- Voice dictation (local Parakeet/Zipformer/Whisper or cloud).

### 3.4 Browser pane & Design Mode
Source: docs/browser/overview, docs/browser/design-mode, docs/recipes/design-mode-fix, issues #15333, #22493

- One Chromium browser per worktree; tabs scoped to worktree; address bar with fuzzy history; devtools opt-in; background loading; scroll positions restored on worktree switch; cookie import from Chrome/Edge; passkey sign-in; browser profiles (own storage partition, UA, viewport); viewport emulation via CDP.
- Design Mode: toggled by a Design Mode button in the browser toolbar; cursor becomes a picker; hover highlights; click captures: the element's outer HTML "and a small neighborhood", computed CSS (colors, fonts, spacing), a cropped screenshot of the element, and source file/line when dev-mode source maps exist. Issue #15333 confirms the internal payload also carries a selector and geometry and that currently only one primary target gets full fidelity with up to 4 lightweight extra references. The element becomes "a rich attachment" in the agent chat/composer; the user then types a natural-language instruction.
- Annotation tray: keep several notes on the page before sending; hover a note for Edit/Save/Cancel; "Send" button in the tray or banner → "Send notes to" dropdown to pick the target agent (mouse-only today; issue #22493 requests shortcuts).
- Exact text format inserted into a raw terminal prompt: [UNVERIFIED].
- Agent access to the same browser via CLI: `orca goto/snapshot/click/fill/wait/screenshot/full-screenshot/pdf/console/network/tab list|create|switch/capture start/set device`. Snapshot returns element refs like `@e3` used by `click --element @e3`.
- Known gap: design mode unavailable in remote-host browser (issue #20441).

### 3.5 Diff viewer & diff annotation
Source: docs/review/diff-viewer, docs/review/annotate-ai-diff, docs/review/attribution, docs/review/commit-push

- Combined diff across staged/unstaged/untracked; compare against start-from ref or any commit/branch; collapsible file tree; collapsible unchanged regions; image diffs; HTML preview eye icon opens working-tree HTML in a side browser split; 3-way merge conflict UI with "Resolve with AI"; stage by hunk or line.
- Shortcuts: j/k file, n/p hunk, s stage hunk, c comment.
- Annotation flow: hover line → plus sign in gutter; click or press c; markdown comment; Cmd-Enter save; multi-line by drag or Shift-extend; comments track across edits and follow shifting lines; "Send to Agent" button at top of diff opens a menu of the worktree's agents; Orca "composes a single prompt with all your comments, line-anchored"; after revision, comments stay visible; Resolve collapses a thread; unresolved comments are re-sent in the next batch.
- Attribution: Orca tracks provenance on every line an agent touches; AI-written lines get a gutter marker in the diff; human edits revert to human; local only (not committed); exportable.
- Source control panel: `branch → base`, one-click stage/commit/push/pull, "Generate with AI" commit message via action recipes, PR composer with AI-drafted title/body, draft state, stacked PRs.

### 3.6 Orca CLI (agents drive Orca)
Source: docs/cli/reference, docs/cli/overview, docs/cli/skills, docs/cli/orchestration, docs/cli/automations, docs/cli/computer-use

Ships with the app; all commands accept `--json`. Agents learn it via skills (`orca skills install --skill orca-cli`; `orca skills get <topic> --full`). Seven skills: orca-cli, orchestration, computer-use, orca-linear, orca-emulator (iOS sim), orca-emulator-android, orca-per-workspace-env.

Command families:
- Runtime: `orca open`, `status`, `serve --port 6768`
- Repo: `repo list|add|show|set-base-ref|search-refs`
- Worktree: `worktree list|ps|current|show|create (--repo --name --agent --prompt --issue --setup)|set (--comment --workspace-status)|rm --force`
- Terminal: `terminal list|show|read (--screen|--cursor --limit)|send --text --enter|wait --for tui-idle --timeout-ms|create --title --command|split --direction|rename|switch|close`
- Files: `file open|diff --staged|open-changed`
- Browser: `goto, snapshot, click --element @eN, fill, wait --text, screenshot, full-screenshot, pdf, tab list|create|switch, capture start, console, network, exec, set device`
- Computer use (desktop apps via accessibility trees): `computer permissions|list-apps|get-app-state|click|paste-text|set-value|type-text|press-key|scroll|drag`
- Emulator: `emulator list|attach|tap|type|gesture|button|rotate|exec|kill|shutdown`
- Search (AI Vault): `search --query --scope conversation --agent --since --sort recent`
- Linear: full issue/project management subcommands
- Skills, Accounts (`account list|add --agent codex`), Artifacts (`artifacts share|update|unshare|list|delete`), Automations (`automations create --trigger hourly|daily|weekdays|weekly|cron|RRULE --prompt --provider --repo`), Environments, Hooks, Hosts
- Orchestration primitives: Run (durable namespace/inbox), Task (states pending/ready/dispatched/completed/failed/blocked), Dispatch, Worker; `orca orchestration worker-start --task --worktree current|new-child --agent codex`; `orca orchestration send --type worker_done --outcome succeeded`; coordinator waits for Deliveries and acks.

### 3.7 Account switcher & usage tracking
Source: docs/agents/usage-tracking, docs/agents/codex-hot-swap

- Status bar segment shows current usage vs active account's plan and time-to-reset for 5-hour, daily, weekly, and Claude Fable weekly windows; warning at 80% of a limit; toggle "% used vs % remaining".
- Usage popover: every tracked provider as icon · name · plan · soonest reset · per-window bars, sorted tightest-limit-first; Detailed vs Compact views; rows drill into account switching; estimated cost for known model families using Orca's local price table.
- Reads on-disk usage state (`~/.claude`, `~/.codex`, Gemini/OpenCode equivalents) — no API calls; scans run on a worker thread.
- Hot-swap: click the Codex (or Claude) chip in the status bar → dropdown of detected accounts with usage/limits; "Orca rewrites the active credential pointer, it does not re-authenticate"; running sessions keep their account until restart; per-project Claude account binding exists.

### 3.8 Mobile companion
Source: docs/mobile, docs/android-apk

"Read-mostly view… a remote control for the desktop you already have running." Shows every worktree, its agent, status (working/done/waiting on input); browse file tree; send short replies, attach photo/file, mic dictation; open sessions in Chat UI transcript or raw terminal; switch active account, view usage/rate limits; source control basics. Pairing via one-time code over LAN, Orca Relay (cloud, sign-in required), or direct. Limitation: "Desktop still owns the agent" unless using a Remote Orca Server.

### 3.9 GitHub / Linear / Jira / Bitbucket integration UI
- GitHub via OAuth or `gh` CLI; "GitHub API Budget" shows quota. Tasks sidebar shows GitHub Projects cards; Roadmap timeline views. Issue drawer; create worktree from an issue. PR tab shows checks, reviews, comments inline; approve/review/draft actions; auto-merge; stacked PRs.
- Linear via personal API token; unified task drawer with GitHub; list/board views; agent prompts include inline images from issue description.
- Jira (Cloud or Server/DC) and Bitbucket Cloud connectable; GitLab MR review actions.

### 3.10 Command palette / search
Source: docs/model/quick-open

- Quick Open Cmd-P: files in current worktree, ranked by recency + match.
- Tab omnibox (+): one field for open tabs, files, URLs, agents, worktree browser history.
- Worktree Jump Palette Cmd-J: jump across every worktree and tab; host/project filters; shows up to six recent sessions ranked needs-you → completed → idle; matches PR/MR titles and numbers; Shift-Enter opens in new split; create worktree from typed text if none matches.
- `orca search` / AI Vault session search across paired machines.

### 3.11 Memory, context, session resume
Source: docs/agents/hooks-memory, docs/agents/session-history, docs/agents/hibernation, docs/model/session-restore

- Orca does not manage agent memory: "Claude's `CLAUDE.md` and Codex's `AGENTS.md`… are left alone — they belong to the agent." It reads `.claude/` and `.codex/` configs and runs existing hooks. Worktree setup hooks per repo; "Worktree Shared Paths" materialize gitignored paths.
- Agent Session History (right sidebar): scans on-disk transcripts of ~17 agents; search by title/cwd/branch/model/preview; Resume button runs `claude --resume <id>` / `codex resume <id>` in a fresh terminal.
- Hibernation (experimental): pauses idle done agents (default 30 min) when not visible; auto-resume via resume flags when worktree reopened.
- Session restore: worktrees, per-worktree layouts, running agents (via daemon), terminal buffers, last view restored on quit/update/crash; "Orca always restores".

### 3.12 Documents / notes / markdown
Source: docs/editing/markdown

- Tiptap-based rich markdown editor: slash menu (headings, lists, code, callouts, images, mermaid, toggle blocks), toolbar, inline image/code previews, `[[` wiki-link autocomplete to worktree paths, table editor, YAML/TOML front matter shown; Cmd-Shift-M toggles raw Monaco.
- Artifacts: "Share as artifact" publishes a markdown file (≤10 MiB) as a public link via an Orca Account (opt-in); agents manage via `orca artifacts`.
- Editor: Monaco with autosave, minimap toggle, viewers for images/HTML, file explorer with git-status colors, drag files onto agent terminal to paste paths.

### 3.13 Native Chat
Experimental structured transcript + composer for Claude, Codex, Grok, OMP, OpenCode sessions; "The terminal remains the source of truth." Elements: grouped tool batches that settle into expandable rows, inline diff cards, plan cards, task checklists + collapsible progress panel above composer, turn file-change rollups, subagent activity, message rail, image attachments, Fast-mode toggle, pulsing Thinking state.

### 3.14 Settings (top-level sections)
General, Appearance (theme, accent, density, App Icon, language EN/中文/한국어/日本語/ES), Git, Terminal, Quick Commands, Agents, Browser, Artifacts, Integrations, Notifications, Voice, SSH, Remote Orca Servers, Shortcuts, Repository, Floating Workspace, Plugins (experimental), Experimental (Activity Page, compact cards, hibernation, Agent Dashboard, Chat UI, Cloud VM), Privacy.

### 3.15 Remote modes
Local; SSH targets; Remote Orca Server (headless `orca serve`; revocable per-client tokens); Cloud VM / per-workspace environments via `orca.yaml` recipes.

## 4. User criticism, known limitations, bugs
- HN (https://news.ycombinator.com/item?id=49233448): mostly praise; requests: hide completed worktrees but keep transcripts; "took about half an hour" to find the diff view (discoverability). General ADE skepticism: Electron GUI irony; npm dependency security.
- HN (https://news.ycombinator.com/item?id=49216491): "These tools casually like to claim they are orchestrators, but unfortunately, none of them are."
- Reviews: Electron RAM 250–800 MB per app, ~10 GB with five agents; 3–5× token/quota burn; daily releases bring regressions "typically fixed within 24 hours"; "a tool that ships daily moves under you"; mobile useless when desktop is off; SSH hosts need toolchain; PostHog telemetry on by default; "more parallel output means more human review".
- GitHub issues: #18173 SSH worktree cards die after restart; #13612 GitHub account per-repo not respected; #13746 stale managed Codex credentials; #18092 preflightTrust writers discard a running agent's config changes; #17397 credential-bearing pairing URLs; #20441 Design Mode missing in remote-host browser; #15333 multi-element design-mode selection; #22493 keyboard shortcut for sending annotations.
- Backlog size (~3k open issues) signals velocity vs. triage.

## 5. Roadmap statements
No formal public roadmap page found [UNVERIFIED]. Signals: Experimental settings list (Agent Dashboard, Chat UI, Hibernation, Cloud VM, Plugins).

## 6. Positioning vs Conductor / Cursor / Warp
- Landing page capability table vs "IDEs and wrappers": parallel agents in isolated worktrees, cross-platform (a dig at Conductor's macOS-only), MIT open source, GPU terminal with splits, embedded Chromium with design mode, 27 agents vs "one or two".
- Terminal docs import Ghostty config and Warp themes — positioning as a terminal replacement too.
- Superset's comparison: Orca wins breadth/openness/cross-platform/mobile; Conductor wins "coordination and polish" (named team roles, context reinjection); Orca = "a fleet of independent agents you supervise".

## Key source URLs
Landing https://www.onorca.dev/ · Docs index https://www.onorca.dev/docs · Changelog https://www.onorca.dev/changelog · Enterprise https://www.onorca.dev/enterprise · Repo https://github.com/stablyai/orca · YC https://www.ycombinator.com/companies/stably-ai-orca · star-history https://www.star-history.com/stablyai/orca/ · Docs pages: /docs/model/{worktrees,tabs-panes-splits,agents-sessions,session-restore,quick-open}, /docs/terminal, /docs/browser/{overview,design-mode,profiles}, /docs/review/{diff-viewer,annotate-ai-diff,attribution,commit-push,github,linear}, /docs/cli/{overview,reference,orchestration,automations,computer-use,worktree-checkpoints,skills}, /docs/agents/{supported,usage-tracking,codex-hot-swap,native-chat,session-history,hibernation,hooks-memory}, /docs/{mobile,notifications,activity,settings,telemetry,ssh,remote-servers,ways-to-run,install} · HN https://news.ycombinator.com/item?id=49233448 , https://news.ycombinator.com/item?id=49216491 · Reviews https://andrew.ooo/posts/orca-stablyai-parallel-coding-agents-ide-review/ , https://vibecodinghub.org/blog/orca-review , https://superset.sh/compare/orca-vs-conductor , https://agentconn.com/blog/orca-ade-agent-fleet-parallel-coding-agents-2026/ , https://aistarted.com/tutorials/orca-open-source-ai-coding-agent-orchestrator/ , https://blog.margrop.net/en/post/orca-parallel-ai-agent-ide-review/
