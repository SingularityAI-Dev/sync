# sync-context-audit

This repo packages `/sync`, an architecture-aware project state-sync command for Claude Code, plus its **Context Audit** pre-run. Read this before editing so changes stay consistent with the command's contract.

## What this is

Two cooperating pieces:

1. **The command** — `sync.md`. A Claude Code slash command (YAML frontmatter + Markdown body, `allowed-tools`: Read, Write, Edit, Bash, Grep, Glob). It detects whether the current directory is a normal project, a Second_Brain vault, or the Vaults orchestrator, then writes only the files that changed (CHANGELOG, STATUS, brain.md), wires `brain.md` into the auto-memory index, and dispatches a one-line update into Second_Brain so cross-project state compounds. Replaces the older `/auto-doc`.

2. **The Context Audit helper** — `lib/context-audit.py` + `lib/context-audit.config.json`. Invoked by `sync.md` Step 1c (project mode only). It discovers the MCP servers, plugins, hooks, and auto-loaded memory a project pulls into the context window, estimates their token weight, and flags what is wasted *for this project*.

## Core principle

Read first, classify, skip files that do not need changes. A sync that touches one file is a success; a sync that writes nothing is also a success. Writing for the sake of writing is failure. Silence beats narration.

## Hard guard (do not weaken)

`/sync` refuses to run at `$HOME`, the parent of `$HOME`, a filesystem root, or any directory with no project signal (no `.git`, no package manifest, and not a vault with `SOUL.md`). When the guard trips it writes nothing. This is deliberate: running at home or system root pollutes per-project state locations.

## Classification model (helper)

Each loaded item gets a verdict (`used` / `unused` / `uncertain`) and an action tier:

- **value-earning** servers (code-intelligence, retrieval — they reduce consumption): kept on code projects, flagged only where there is no code.
- **domain** servers: `used` only when a matching project signal is present (`dep:<pkg>`, `file:<name>`, `dir:<name>`, `gitremote:<host>`).
- **infra (never-touch)**: never flagged. Checked first, before the value-earning heuristic, to avoid substring collisions (e.g. `context7` contains `context`).
- **unknown** servers: `uncertain` — the helper takes no action; the model decides.

Action follows scope: project-`.mcp.json` servers can be auto-disabled on confirm via `disabledMcpjsonServers`; globally/user-scoped servers are recommend-only. The helper never writes global config or any CLAUDE.md.

## Layout

```
sync.md                          the command (installs to ~/.claude/commands/)
lib/context-audit.py             the audit helper (installs to ~/.claude/commands/lib/)
lib/context-audit.config.json    the tuning surface (installs beside the helper)
install.sh                       copies the above into place
tests/test_context_audit.py      pytest suite for the helper
docs/                            Superpowers design + plan docs, and how-it-works writeup
```

## Working on this repo

- Install locally with `./install.sh`, then run `/sync` inside any project.
- Verify the helper standalone: `python3 ~/.claude/commands/lib/context-audit.py --project "$PWD" --format text`
- Run tests: `python3 -m pytest -q`
- `sync.md` here is the source of truth; `~/.claude/commands/sync.md` is the installed copy. Edit here, then re-run `install.sh`.
- Token figures are estimates (`/context` numbers are not exposed to commands). MCP/plugin changes take effect on the next session, not the current one.

## Conventions

- No em-dashes anywhere.
- The config (`lib/context-audit.config.json`) is the only thing a new user should need to edit; nothing is hardcoded to one machine. Paths derive from `$HOME` and the project path.
