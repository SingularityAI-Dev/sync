# Design: /sync Context Audit pre-run

> Date: 2026-05-29
> Status: approved-pending-review
> Owner: Rainier (Geez)

## Problem

`/sync` writes per-project state and dispatches to Second_Brain. It has no awareness
of the *context window* it runs inside. Every Claude Code session loads MCP server
tool definitions, plugins, hooks, and auto-loaded memory files. Much of that is
irrelevant to the current project and silently wastes tokens on every future session.

The user wants `/sync` to keep doing its job, but gain a pre-run that sees where
context is being wasted for *this* project and trims what it safely can, recommending
the rest. It must be intelligent on the user's own machine and packageable as a
generic tool to share with others (no hardcoded identity, no hardcoded server list).

## Hard constraints (verified against current Claude Code docs, 2026-05)

1. `/context` is a client-side TUI command. It cannot be invoked by a custom slash
   command or the model, and its numbers are not exposed programmatically. The audit
   must reproduce the relevant signal itself from config + filesystem, and label all
   token figures as estimates.
2. A project `.claude/settings.json` can disable **only** MCP servers defined in a
   project-local `.mcp.json` (`disabledMcpjsonServers` / `enabledMcpjsonServers`).
   It **cannot** disable globally/user-scoped MCP servers (those in `~/.claude.json`
   `mcpServers`) or account-level claude.ai connectors.
3. Per-project plugin disabling via `enabledPlugins` has undocumented merge semantics
   (replace vs union); not reliable, so not used for auto-action.
4. `disableAllHooks` is all-or-nothing per scope; too blunt for selective hook trim.
5. MCP/plugin config changes take effect next session (or via `/reload-plugins`),
   not in the current window. The payoff is compounding, not instant.

Net: the only safe, reliable per-project auto-actions are (a) pruning the memory
`/sync` already owns, and (b) disabling project-`.mcp.json` servers. Everything
global/user-scoped is **recommend-only**.

## Goal

A `Context Audit` stage inside `/sync`, project mode only, that runs after the Step 1
hard guard and mode detection and before the existing read/classify/write pipeline.
It never alters `/sync`'s existing behaviour; it prepends an awareness-and-trim pass.

Chosen approach: **A — act-where-safe, recommend-the-rest**. Safety posture:
**recommend, apply on confirm**. Categories in scope: MCP servers, plugins, memory
files, hooks.

## Architecture

Two cooperating pieces:

### 1. `context-audit.py` (deterministic, generic, token-cheap)

A standalone Python helper. Takes no identity input; derives everything from `$HOME`
and the target project path (passed as `--project <path>`, default cwd). Prints a
compact JSON report to stdout. Responsibilities:

- **Discover** (never hardcode):
  - Global + project MCP servers from `~/.claude.json` (`mcpServers`,
    `projects[<path>].mcpServers`) and project `.mcp.json`.
  - Enabled plugins from `~/.claude/settings.json`, project `.claude/settings.json`,
    `.claude/settings.local.json` (`enabledPlugins`).
  - Hooks from the same settings files (`hooks`, `disableAllHooks`).
  - Owned memory files in `~/.claude/projects/<slug>/memory/` (sizes of `MEMORY.md`,
    `brain.md`, typed `*_*.md`). `<slug>` = project path with `/` → `-`.
- **Estimate weight** (labelled approximate): MCP server = tool_count × per_tool_tokens
  (default 150); plugin = injected skills/commands/hooks count × constants; memory
  file = bytes ÷ 4. Tool counts read from each server's advertised tool list where
  available, else a configured default.
- **Detect project type**: `code` (has package manifest / source files), `docs-vault`
  (has `SOUL.md` or is predominantly `.md`), or `unknown`.
- **Classify** each item via `context-audit.config.json` (shipped defaults,
  user-overridable):
  - `value_earning`: servers that *reduce* consumption (e.g. code-intelligence /
    context-retrieval servers). Kept on matching project types; flagged only where the
    project type makes their value impossible (e.g. a code-intel server on a docs-vault).
    Seeded with examples (jcodemunch), but primarily matched by a tool-signature
    heuristic so unknown servers of the same kind are caught.
  - `domain`: servers/plugins useful only for a domain (analytics, deploy, tickets).
    `used` if a project signal matches, else `unused`.
  - `infra_never_touch`: never flagged (docs lookups, core infra).
  - `domain_signals`: map of item → project signals (deps, files, git remote host).
- **Emit verdict + tier** per item: verdict ∈ {used, unused, uncertain}; tier ∈
  {auto-safe (memory / project-`.mcp.json`), recommend (global/user-scoped),
  none}. For `recommend`, include the exact fix command. Size is only the report
  sort key, never the action trigger.

Output shape (JSON): `{ project_type, slug, items: [{category, name, est_tokens,
verdict, tier, reason, fix_command?}], totals: {est_loaded, est_reclaimable_auto,
est_reclaimable_recommend}, uncertain: [names] }`.

### 2. `sync.md` Context Audit stage (judgment + action)

- Runs `context-audit.py --project <cwd>`, reads the JSON.
- For `uncertain` items only, applies model judgment using project context already in
  hand, settling them to used/unused.
- Presents the ranked audit block. For `auto-safe` `unused` items, proposes the
  specific edits (memory prune; add to project `disabledMcpjsonServers`) and applies
  **only on user confirm**.
- Lists `recommend` items as one-liners with fix commands; never edits global config,
  never edits any CLAUDE.md.
- Memory pruning merges into the existing Step 5 memory writes rather than duplicating.

## Output (added to the /sync report)

```
Context Audit (project type: <type>)  — estimates, next-session effect
  Loaded ~<N>k tokens of tooling/memory; ~<M>k reclaimable here.
  category   item            est     verdict    action
  mcp        <server>        ~15k    unused     recommend: <cmd>
  mcp(.mcp)  <server>        ~3k     unused     applied: disabledMcpjsonServers
  memory     <file>          ~2k     stale      applied: pruned
  plugin     <name>          ~1k     uncertain  none (kept)
  Nothing else material.
```

If nothing is wasteful: `Context audit: nothing material.`

## Guardrails

- Inherits `/sync`'s hard guard (project mode only; never at $HOME/root).
- Never edits global config (`~/.claude.json`, `~/.claude/settings.json`) or any
  CLAUDE.md automatically.
- Nothing disabled without explicit confirm.
- Every applied change listed for one-step revert.
- All token numbers labelled estimates; effect is next-session, stated plainly.
- Unknown/uncertain items default to keep, never auto-disable.

## Portability / packaging

- Zero hardcoded usernames, slugs, or server names in code; all derived or in the
  editable config file.
- Bundle for sharing: `sync.md`, `lib/context-audit.py`, `context-audit.config.json`
  (documented defaults), `README.md`, `install.sh`. Mirrors the existing
  sync-command-package layout.
- The shipped config is the single tuning surface: a recipient edits `value_earning`,
  `domain_signals`, and `infra_never_touch` for their own tools; the discovery and
  estimation logic needs no changes.

## Out of scope (v1)

- Vault/orchestrator mode auditing (project mode only first).
- Touching global config automatically.
- Exact token accounting matching `/context` (not exposed; estimates only).
- Auto-disabling user-scoped plugins (unreliable semantics; recommend-only).

## Testing

- Unit: `context-audit.py` against fixture config dirs (code project, docs-vault,
  unknown) → asserts verdicts/tiers for seeded servers and a synthetic unknown server.
- Estimation: byte/tool-count math is deterministic; assert against known fixtures.
- Dry-run: run against a real project and the Second_Brain vault; confirm jcodemunch
  is kept on code, flagged only on the vault; confirm no global file is written.
