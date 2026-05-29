---
name: sync
description: Sync project state. Detects architecture (project, Second_Brain vault, or Vaults orchestrator), writes only what changed, wires brain.md into auto-memory, and dispatches a one-line update into Second_Brain so cross-project state compounds. Replaces /auto-doc.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
---

# /sync: Project Sync

One pass. Architecture-aware. Selective writes. Cross-project compounding.

## Core principle

**Read first. Classify. Skip files that don't need changes.**

A sync that touches one file is a successful sync. A sync that writes nothing is also a successful sync. Writing for the sake of writing is failure. Token-efficient by default; silence beats narration.

## Architecture detection (Step 1, always)

### Step 1a: Hard guard — refuse to run at system root

**Abort immediately, write nothing**, if cwd is any of:

- `$HOME` itself (e.g. `/Users/rainierpotgieter`)
- The parent of `$HOME` (e.g. `/Users`)
- A filesystem root (`/`, `/tmp`, `/etc`, `/var`, `/opt`, etc.)
- Any path with no enclosing project signal: no `.git`, no `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` / `Gemfile` / equivalent, AND not a vault (no `SOUL.md`).

When aborting, emit exactly:

```
/sync refuses to run here. cwd=<cwd> is not a project.
cd into a project directory (something with a .git, package manifest, or vault SOUL.md) and re-run.
```

Do not write CHANGELOG, STATUS, brain.md, typed memory, or Second_Brain dispatch when this guard trips. The whole point of /sync is per-project state; running it at the user's home or system root pollutes those locations and is never wanted.

### Step 1b: Detect mode by inspecting cwd

| Signal in cwd | Mode | Why |
|---|---|---|
| Has `SOUL.md` AND `HEARTBEAT.md` AND `daily/` | **Vault mode** (inside a Second_Brain vault) | The vault is itself a memory architecture. Use its schema. |
| Has subdirs that each look like vaults (any with `SOUL.md`) and a `Vaults/` lineage in path | **Orchestrator mode** | Multi-vault parent. Don't write inside child vaults. |
| Otherwise (regular repo or directory that passed Step 1a) | **Project mode** | Write the standard trio: CHANGELOG, STATUS, brain. |

In **Project mode**, also check whether `~/development/Vaults/Second_Brain/` exists. If yes, **dispatch is enabled**: a compressed update will be written into Second_Brain so cross-project state compounds. If not, skip dispatch silently.

`<project-slug>` is the cwd path with `/` replaced by `-`, leading `-` preserved. Example: `/Users/rainierpotgieter/development/Foo` becomes `-Users-rainierpotgieter-development-Foo`.

### Step 1c: Context audit (project mode only)

Before reading project state, run the context-audit helper to see what tooling and memory this project loads and what is wasted here. Helper path: `~/.claude/commands/lib/context-audit.py`.

Run: `python3 ~/.claude/commands/lib/context-audit.py --project "$PWD" --format json`

From the JSON report:
- **uncertain[]**: for each, decide used/unused yourself using project context already in hand (what the repo is, its stack, what this session did). Do not auto-disable an uncertain item; if you judge it clearly unused and heavy, move it to the recommend list, never to auto-action.
- **tier == "auto-safe"** (memory oversize; project `.mcp.json` servers): propose the concrete edit and apply ONLY on user confirm. Memory pruning folds into Step 5 (do not double-write). For a project `.mcp.json` server, add its name to `disabledMcpjsonServers` in the project `.claude/settings.json`.
- **tier == "recommend"** (global/user-scoped servers, plugins): list as one-liners with the provided `fix_command`. NEVER edit global config (`~/.claude.json`, `~/.claude/settings.json`) or any CLAUDE.md.

Render the audit as the first block of the final report (see Step 7). All token numbers are estimates; state that the effect is next-session. If the helper is missing or errors, skip silently and note one line: "Context audit: helper unavailable."

Skip this step entirely in vault and orchestrator mode.

## Artifacts by mode

### Project mode (default)

| File | Location | Cap | Purpose |
|---|---|---|---|
| `CHANGELOG.md` | project root | ~40 lines / 20 entries | Rolling log of meaningful changes |
| `STATUS.md` | project root | ~80 lines | Current state + next, snapshot-style |
| `brain.md` | `~/.claude/projects/<slug>/memory/brain.md` | ~60 lines | Durable per-project session memory |
| `MEMORY.md` | `~/.claude/projects/<slug>/memory/MEMORY.md` | <200 lines | Auto-memory index. Must point at `brain.md`. |
| Typed memory files | `~/.claude/projects/<slug>/memory/<type>_<slug>.md` | small | `feedback_*`, `project_*`, `reference_*`, `user_*` per global schema |
| Second_Brain dispatch | `Vaults/Second_Brain/daily/YYYY-MM-DD.md` (append) + `MEMORY.md` "Active Projects" line | 1-3 lines per sync | Cross-project consciousness |

### Vault mode (inside Second_Brain or Second_Brain_Hermes)

| File | Location | Action |
|---|---|---|
| `daily/YYYY-MM-DD.md` | vault root | **Append** a timestamped block. This is the canonical short-term log. |
| `CHANGELOG.md` | vault root | Update if a real change shipped (cap 20). |
| `SOUL.md`, `USER.md`, `HABITS.md` | vault root | **Never touch.** Identity layer. |
| `MEMORY.md` | vault root | **Never touch directly.** Daily reflection promotes from `daily/`. /sync is not reflection. |
| `HEARTBEAT.md` | vault root | **Never touch.** It is a monitoring checklist, not a state file. |

### Orchestrator mode (at `Vaults/` root)

Only maintain the orchestrator's own `CHANGELOG.md` / `STATUS.md` if they exist. **Never write into child vaults.** Recommend the user run `/sync` inside the specific vault instead. Surface this as the final-report nudge.

## Process

### Step 0: Legacy migration (one-time, project mode only)

If `PROGRESS.md` or `ROADMAP.md` exists in project root:
1. Fold `PROGRESS.md`'s Current/Recently/In-Progress into STATUS.md's "Where we are" + "Recent". Drop stale "Blocked" sections.
2. Fold `ROADMAP.md`'s Now/Next/Later into STATUS.md's "Next". Drop completed items.
3. If STATUS.md already exists, **merge.** Prefer existing content on conflict.
4. Flatten version-tagged CHANGELOG entries to one-line format, keep last 20.
5. Delete `PROGRESS.md` and `ROADMAP.md`. Note removal in final report.

Skip in vault/orchestrator mode; those schemas predate auto-doc.

### Step 2: Read existing state (parallel)

- Read existing `CHANGELOG.md`, `STATUS.md`, `brain.md`, `MEMORY.md` (project memory dir).
- Read `Second_Brain/MEMORY.md` and today's `Second_Brain/daily/YYYY-MM-DD.md` if dispatch is enabled (project mode only).
- `git log --oneline -20` and `git status --short` for ground truth.
- `date +%Y-%m-%d`.

### Step 3: Classify candidates from the conversation

Scan the conversation (and any pre-compaction notes) for four signals. Tag each; don't write yet.

| Signal | Routes to |
|---|---|
| Concrete shipped change (code merged, feature done, bug fixed) | CHANGELOG candidate |
| Shift in direction, new constraint, decision about where we're going | STATUS candidate |
| Current active task with enough detail to resume cold; asset exchanged (screenshot, template, draft); durable fact about app purpose | **brain.md** candidate |
| User correction or validated approach ("don't do X", "yes exactly that") | **`feedback_*.md`** candidate (with `**Why:**` + `**How to apply:**`) |
| Who's doing what, why, by when (project / initiative facts not in code or git) | **`project_*.md`** candidate |
| External system pointer (Linear project, Slack channel, dashboard URL) | **`reference_*.md`** candidate |
| Detail about the user's role, expertise, preferences | **`user_*.md`** candidate |
| Recurring correction, missing capability, stale config | improve-sweep candidate (Step 6) |

**Brain.md vs typed files: different half-lives.**
- **brain.md** is "now": active task, in-play assets, recent decisions. Replaced often.
- **typed files** are "durable truths": feedback rules, project facts, references, user profile. Each one focused, indexed in MEMORY.md, surface on-demand.

When in doubt about durability: typed file (cheap to prune, expensive to re-derive).

### Step 4: Decide which files actually need updates

For each artifact, ask: **did Step 3 produce a candidate for this file?** If no, skip. Do not rewrite timestamps. Do not touch unchanged files.

### Step 5: Write (per mode)

#### Project mode

**CHANGELOG.md:** prepend new entries. One line each. Cap 20.
```markdown
# Changelog

> Last 20 changes. Full history in git.

- YYYY-MM-DD: one-line change description
```

**STATUS.md:** rewrite (snapshot, not append). Hard 80-line cap.
```markdown
# Status

> Updated: YYYY-MM-DD

## Where we are
[1-3 sentences. Current state + the why. Replace fully each sync.]

## Recent
- [1-3 major moves with context. Drop items older than ~2 weeks unless still load-bearing.]

## Next
- [Forward-only. No completed items.]
```

**brain.md:** hard 60-line cap.
```markdown
# Brain: <project name>

> Updated: YYYY-MM-DD

## Active task
[Resume-cold detail. Include the why. Replace fully when active task changes.]

## Assets in play
- <type>: <path or description> (why it matters)

## Durable facts
- <fact that would be painful to re-derive>

## Decisions
- YYYY-MM-DD: <decision> (why)
```

Pruning when at cap: never prune Active task; drop assets >14 days unreferenced; compress decisions >60 days; keep durable facts unless obviously stale.

**Typed memory files:** one per durable signal. Schema (matches global auto-memory CLAUDE.md):
```markdown
---
name: <kebab-slug>
description: <one-line summary used for relevance scoring in future sessions>
metadata:
  type: <feedback | project | reference | user>
---

<For feedback/project: lead with the rule/fact, then **Why:** and **How to apply:** lines. Link related memories with [[their-name]].>
```

**MEMORY.md auto-wire:** after writing brain.md or any typed file, ensure `~/.claude/projects/<slug>/memory/MEMORY.md` has an index line for each. MEMORY.md is the only file auto-loaded at session start; if brain.md isn't indexed, fresh sessions never see it.

MEMORY.md format (the index, no frontmatter, ≤200 lines):
```markdown
# Memory Index

- [Brain](brain.md): active task, in-play assets, recent decisions
- [<Title>](<file>.md): one-line hook
```

Always keep `[Brain](brain.md)` as the first entry. Add lines for typed files when created. Remove lines when files deleted. Update hooks when descriptions drift.

**Second_Brain dispatch** (only if `~/development/Vaults/Second_Brain/` exists):

1. **Append to `Second_Brain/daily/YYYY-MM-DD.md`.** Create if missing. Block format:
   ```markdown
   
   ## HH:MM: sync from <project-name>
   - Active: <one-line active task>
   - <Shipped|Decided|Noted>: <one line> (optional, only if material)
   ```
   1-3 lines max. No padding. Skip the dispatch entirely if Step 3 found nothing material.

2. **Update `Second_Brain/MEMORY.md`.** Find or create an `## Active Projects` section. Each line is `- **<project-name>**: <one-line current state> (<YYYY-MM-DD>)`. Update in place if the line for this project exists; insert if not. Drop lines for projects whose date is older than 30 days (they've gone dormant). Never touch other sections of Second_Brain/MEMORY.md; daily reflection owns those.

Dispatch rules:
- **Never fabricate.** If nothing material happened, write nothing.
- **No cross-section spillage.** Only `## Active Projects` in MEMORY.md is /sync's territory.
- **One project, one line** in Second_Brain/MEMORY.md. Compression discipline.

#### Vault mode

Append to `daily/YYYY-MM-DD.md` (create if missing):
```markdown

## HH:MM: sync
- <one line per material signal: shipped, decided, noted>
```

Update vault `CHANGELOG.md` only if a concrete change shipped (cap 20). Leave SOUL/USER/MEMORY/HEARTBEAT/HABITS alone; reflection owns MEMORY, the user owns the rest.

#### Orchestrator mode

Maintain only the orchestrator's own `CHANGELOG.md`/`STATUS.md` if they exist. End the report with: `Run /sync inside <vault-name>/ to update that vault's daily log.`

### Step 6: Friction sweep (quiet)

Scan for: repeated user corrections, manual workarounds for things that should be automated, permissions repeatedly approved, stale config referencing missing tools/files.

**If high-signal**: surface ONE sentence at end of report, no edits. **If low-signal**: silence. Point at `/improve` if the user wants a full sweep.

### Step 7: Report

Concise. One line per file touched.

```
Context Audit (project type: <type>) — estimates, next-session effect
  Loaded ~<N>k est; reclaimable ~<A>k auto, ~<R>k via recommendations.
  <ranked rows: category · item · est · verdict · applied/recommended/none>
  [recommendations as one-liners with exact commands]

Sync complete. (mode: project | vault | orchestrator)
- CHANGELOG.md: +2 entries (oldest 1 dropped)
- STATUS.md: unchanged
- brain.md: +1 asset, +1 decision
- MEMORY.md (auto-memory): wired Brain entry
- feedback_<slug>.md: created
- Second_Brain dispatch: +1 daily line, MEMORY.md Active-Projects updated
[Optional: friction nudge]
```

Migration line ("Migrated PROGRESS + ROADMAP into STATUS, deleted") only when Step 0 actually moved something.

If nothing written: `Sync complete. No meaningful changes to record.`

## Rules

- **Never fabricate.** Evidence in conversation, git, or files, or don't write it.
- **Replace, don't append**, for snapshot files (STATUS, brain). Only CHANGELOG and `daily/` are logs.
- **Respect caps.** ~40 / ~80 / ~60 / ~200 lines. Prune before exceeding.
- **No emoji. No banners.** Developer's notebook, not marketing.
- **No em-dashes.** Use commas, semicolons, colons, full stops.
- **CLAUDE.md is sacred.** /sync never edits any project-level or vault-level CLAUDE.md. If something belongs there, mention it via the friction sweep.
- **Second_Brain/MEMORY.md is mostly sacred.** /sync only owns its `## Active Projects` section. Daily reflection owns the rest.
- **brain.md must be indexed in MEMORY.md.** Otherwise it never surfaces in fresh sessions; that is the whole point.
- **Vault SOUL/USER/HEARTBEAT/HABITS** are never touched by /sync. Identity is the user's, monitoring is the heartbeat script's.
- **Context audit never touches global config.** It may only edit project `.claude/settings.json` (and only `disabledMcpjsonServers`), and only on confirm. Global MCP servers, user plugins, and CLAUDE.md are recommend-only.
- **Audit estimates are approximate.** Never present them as exact `/context` numbers; always note the effect is next-session.
