# /sync + Context Audit

`/sync` is an architecture-aware project state-sync command for Claude Code. This
bundle adds a **Context Audit** pre-run: before syncing, it discovers the MCP servers,
plugins, hooks, and auto-loaded memory this project pulls into the context window,
estimates their token weight, and flags what is wasted *for this project* — trimming
the safe project-scoped items on your confirm and recommending the rest.

Token figures are estimates (Claude Code's `/context` numbers are not exposed to
commands). MCP/plugin changes take effect on the **next** session, not the current one.

## Layout

```
sync.md                          the command (install to ~/.claude/commands/)
lib/context-audit.py             the audit helper (install to ~/.claude/commands/lib/)
lib/context-audit.config.json    the tuning surface (installs beside the helper)
install.sh                       copies the above into place
tests/                           pytest suite for the helper
```

## Install

```bash
./install.sh
```

Then run `/sync` inside any project. Verify the helper standalone with:

```bash
python3 ~/.claude/commands/lib/context-audit.py --project "$PWD" --format text
```

## How classification works

Per project, each loaded item gets a verdict (`used` / `unused` / `uncertain`) and an
action tier:

- **value-earning** servers (code-intelligence, retrieval — they *reduce* consumption):
  kept on code projects, flagged only where there is no code to analyze (e.g. a docs
  vault).
- **domain** servers: `used` only when a matching project signal is present
  (`dep:<pkg>`, `file:<name>`, `dir:<name>`, `gitremote:<host>`), else flagged.
- **infra** (never-touch) servers/plugins: never flagged.
- **unknown** servers: `uncertain` — the helper takes no action; `/sync` (the model)
  decides using project context.

Action tier follows scope: project-`.mcp.json` servers can be auto-disabled (on
confirm) via `disabledMcpjsonServers`; globally/user-scoped servers are **recommend
only** (a project cannot disable a global server — the helper prints the exact
`claude mcp` command instead). The helper never writes global config or any CLAUDE.md.

## Tuning (the generic surface)

Edit `lib/context-audit.config.json`:

- `value_earning` — `names` and `tool_signatures`. A server matches if its name is in
  `names` OR contains one of the `tool_signatures` substrings. Kept on code projects,
  flagged only where there is no code.
- `domain_signals` — map of server/plugin name → project signals that mark it used.
- `infra_never_touch` — servers/plugins never flagged. **Checked first**, before the
  value-earning heuristic. This matters: a server whose name contains a signature
  substring (e.g. `context7` contains `context`) would otherwise be miscategorised as
  value-earning. Keeping it in `infra_never_touch.names` short-circuits that. If you
  remove such an entry, tighten the relevant `tool_signatures` token to avoid the
  collision.
- `known_tool_counts` — per-server tool counts for sharper token estimates (read them
  off `/context` once). Unknown servers use `default_tool_count`.
- `per_tool_tokens`, `memory_chars_per_token`, `min_flag_tokens`, `memory_caps_lines` —
  estimation and threshold knobs.

Nothing is hardcoded to one machine: the helper derives all paths from `$HOME` and the
project path and discovers whatever is configured. The config is the only thing a new
user edits.

## Tests

```bash
python3 -m pytest -q
```
