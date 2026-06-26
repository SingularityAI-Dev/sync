#!/usr/bin/env python3
"""Context audit for /sync. See docs/how-sync-works.md for the design rationale."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path

DEFAULTS = {
    "per_tool_tokens": 150,
    "default_tool_count": 25,
    "memory_chars_per_token": 4,
    "min_flag_tokens": 1000,
    "known_tool_counts": {},
    "value_earning": {"names": [], "tool_signatures": []},
    "infra_never_touch": {"names": [], "plugins": []},
    "domain_signals": {},
    "memory_caps_lines": {"MEMORY.md": 200, "brain.md": 60, "typed": 40},
    # Cross-project dispatch target. Optional: dispatch only activates if this
    # directory exists. Set to "" to disable dispatch regardless of the filesystem.
    "second_brain_path": "~/development/Vaults/Second_Brain",
}

def _warn(msg):
    print(f"context-audit: warning: {msg}", file=sys.stderr)

def load_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    if path and Path(path).exists():
        user = json.loads(Path(path).read_text())
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg

def slug_for(project_path):
    return str(Path(project_path)).replace("/", "-")

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".turbo"}
_CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".java", ".c", ".cpp", ".swift"}
_MANIFESTS = ["package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle"]

def _iter_files(root, limit=400):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for f in filenames:
            yield Path(dirpath) / f
            n += 1
            if n >= limit:
                return

def detect_project_type(project_path):
    project_path = Path(project_path)
    if any((project_path / m).exists() for m in _MANIFESTS):
        return "code"
    if (project_path / "SOUL.md").exists():
        return "docs-vault"
    md = code = 0
    for p in _iter_files(project_path):
        s = p.suffix.lower()
        if s == ".md":
            md += 1
        elif s in _CODE_EXT:
            code += 1
    if code >= 3:
        return "code"
    if md > 0 and md >= (code + md) * 0.8:
        return "docs-vault"
    return "unknown"

def _git_remote_host(project_path):
    cfg = Path(project_path) / ".git" / "config"
    if not cfg.exists():
        return None
    m = re.search(r"(github|gitlab|bitbucket|linear)", cfg.read_text(errors="ignore"), re.I)
    return m.group(1).lower() if m else None

def detect_project_signals(project_path):
    project_path = Path(project_path)
    sigs = set()
    pkg = project_path / "package.json"
    if pkg.exists():
        try:
            d = json.loads(pkg.read_text())
            for sec in ("dependencies", "devDependencies", "peerDependencies"):
                for name in (d.get(sec) or {}):
                    sigs.add(f"dep:{name}")
        except Exception as e:
            _warn(f"could not parse {pkg}: {e}; skipping dependency signals")
    for reqfile in ("requirements.txt", "pyproject.toml"):
        f = project_path / reqfile
        if f.exists():
            for token in re.findall(r"[A-Za-z0-9_.-]+", f.read_text(errors="ignore")):
                sigs.add(f"dep:{token.lower()}")
    if project_path.exists():
        for entry in project_path.iterdir():
            sigs.add(("dir:" if entry.is_dir() else "file:") + entry.name)
    host = _git_remote_host(project_path)
    if host:
        sigs.add(f"gitremote:{host}")
    return sigs

_SCOPE_RANK = {"global": 0, "project-user": 1, "project-mcpjson": 2}

def load_claude_json(home):
    p = Path(home) / ".claude.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        _warn(f"could not parse {p}: {e}; treating as empty")
        return {}

def discover_mcp_servers(home, project_path):
    cj = load_claude_json(home)
    servers = []
    for name in (cj.get("mcpServers") or {}):
        servers.append({"name": name, "scope": "global"})
    pnode = (cj.get("projects") or {}).get(str(Path(project_path))) or {}
    for name in (pnode.get("mcpServers") or {}):
        servers.append({"name": name, "scope": "project-user"})
    mcpjson = Path(project_path) / ".mcp.json"
    if mcpjson.exists():
        try:
            d = json.loads(mcpjson.read_text())
            for name in (d.get("mcpServers") or {}):
                servers.append({"name": name, "scope": "project-mcpjson"})
        except Exception as e:
            _warn(f"could not parse {mcpjson}: {e}; skipping project .mcp.json servers")
    return servers

def dedupe_servers(servers):
    best = {}
    for s in servers:
        cur = best.get(s["name"])
        if cur is None or _SCOPE_RANK[s["scope"]] > _SCOPE_RANK[cur["scope"]]:
            best[s["name"]] = s
    return list(best.values())

def settings_files(home, project_path):
    return [
        Path(home) / ".claude" / "settings.json",
        Path(project_path) / ".claude" / "settings.json",
        Path(project_path) / ".claude" / "settings.local.json",
    ]

def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        _warn(f"could not parse {path}: {e}; treating as empty")
        return {}

def discover_plugins(home, project_path):
    found = {}
    for sf in settings_files(home, project_path):
        if sf.exists():
            for p in (_read_json(sf).get("enabledPlugins") or []):
                found[p] = sf.name
    return [{"name": k, "source": v} for k, v in found.items()]

def discover_hooks(home, project_path):
    hooks = []
    for sf in settings_files(home, project_path):
        if sf.exists():
            h = _read_json(sf).get("hooks") or {}
            for event, entries in h.items():
                count = len(entries) if isinstance(entries, list) else 1
                hooks.append({"event": event, "source": sf.name, "count": count})
    return hooks

def measure_memory(home, project_path):
    slug = slug_for(project_path)
    mem_dir = Path(home) / ".claude" / "projects" / slug / "memory"
    files = []
    if mem_dir.exists():
        for f in sorted(mem_dir.glob("*.md")):
            text = f.read_text(errors="ignore")
            files.append({"name": f.name, "bytes": len(text.encode()), "lines": text.count("\n") + 1})
    return {"dir": str(mem_dir), "files": files}

def est_server_tokens(name, cfg):
    tc = cfg["known_tool_counts"].get(name, cfg["default_tool_count"])
    return tc * cfg["per_tool_tokens"], tc

def est_memory_tokens(nbytes, cfg):
    return nbytes // cfg["memory_chars_per_token"]

def is_value_earning(name, cfg):
    if name in cfg["value_earning"]["names"]:
        return True
    sigs = cfg["value_earning"]["tool_signatures"]
    return any(sig in name.lower() for sig in sigs)

def _flag(base, scope, name, reason, cfg):
    # Too small to be worth acting on: report as unused but take no action.
    if base["est_tokens"] < cfg["min_flag_tokens"]:
        return {**base, "verdict": "unused", "tier": "none", "reason": reason + " (below action threshold)"}
    if scope == "project-mcpjson":
        return {**base, "verdict": "unused", "tier": "auto-safe", "reason": reason,
                "action": "add to disabledMcpjsonServers in project .claude/settings.json"}
    if scope == "project-user":
        cmd = f"claude mcp remove {name}  # project-scoped server; remove if unused here"
    else:
        cmd = f"claude mcp remove {name} -s user  # or re-scope to only the projects that use it"
    return {**base, "verdict": "unused", "tier": "recommend", "reason": reason, "fix_command": cmd}

def classify_server(server, project_type, project_signals, cfg):
    name, scope = server["name"], server["scope"]
    est, tc = est_server_tokens(name, cfg)
    base = {"category": "mcp", "name": name, "scope": scope, "est_tokens": est, "tool_count": tc}
    if name in cfg["infra_never_touch"]["names"]:
        return {**base, "verdict": "used", "tier": "none", "reason": "infra (never trimmed)"}
    if is_value_earning(name, cfg):
        if project_type == "code":
            return {**base, "verdict": "used", "tier": "none",
                    "reason": "value-earning (reduces consumption) on code project"}
        return _flag(base, scope, name,
                     f"value-earning server but project type is {project_type}: no code to analyze", cfg)
    signals = cfg["domain_signals"].get(name)
    if signals is not None:
        if any(s in project_signals for s in signals):
            return {**base, "verdict": "used", "tier": "none", "reason": "domain signal present"}
        return _flag(base, scope, name, "domain server with no matching project signal", cfg)
    return {**base, "verdict": "uncertain", "tier": "none", "reason": "unclassified; sync.md applies judgment"}

def _classify_memory(mem, cfg):
    items = []
    caps = cfg["memory_caps_lines"]
    for f in mem["files"]:
        est = est_memory_tokens(f["bytes"], cfg)
        if f["name"] in ("MEMORY.md", "brain.md"):
            cap = caps.get(f["name"])
        else:
            cap = caps.get("typed")
        over = cap is not None and f["lines"] > cap
        items.append({
            "category": "memory", "name": f["name"], "est_tokens": est,
            "verdict": "oversized" if over else "ok",
            "tier": "auto-safe" if over else "none",
            "reason": f"{f['lines']} lines vs cap {cap}" if over else "within cap",
            **({"action": "prune in /sync Step 5 memory write"} if over else {}),
        })
    return items

def resolve_second_brain(cfg, home):
    """Resolve the configured Second_Brain dispatch root and whether dispatch fires.

    Dispatch is a bonus, never a prerequisite: it activates only when the configured
    directory exists. The path is configurable via `second_brain_path` in the config;
    set it to "" (or remove it) to disable dispatch regardless of the filesystem.
    `~` expands against the given `home`, so the result is deterministic and testable.
    """
    raw = (cfg.get("second_brain_path") or "").strip()
    if not raw:
        return {"configured": "", "path": None, "exists": False, "dispatch_enabled": False}
    expanded = os.path.expandvars(raw)
    if expanded == "~":
        expanded = str(Path(home))
    elif expanded.startswith("~/"):
        expanded = str(Path(home) / expanded[2:])
    path = Path(expanded)
    exists = path.is_dir()
    return {"configured": raw, "path": str(path), "exists": exists, "dispatch_enabled": exists}

def build_report(home, project_path, cfg):
    ptype = detect_project_type(project_path)
    signals = detect_project_signals(project_path)
    servers = dedupe_servers(discover_mcp_servers(home, project_path))
    items = [classify_server(s, ptype, signals, cfg) for s in servers]
    items += _classify_memory(measure_memory(home, project_path), cfg)
    for p in discover_plugins(home, project_path):
        verdict = "used" if p["name"].split("@")[0] in cfg["infra_never_touch"]["plugins"] else "uncertain"
        items.append({"category": "plugin", "name": p["name"], "est_tokens": 0,
                      "verdict": verdict, "tier": "none", "reason": f"from {p['source']}"})
    for h in discover_hooks(home, project_path):
        items.append({"category": "hook", "name": f"{h['event']}({h['count']})", "est_tokens": 0,
                      "verdict": "info", "tier": "none", "reason": f"from {h['source']}"})
    items.sort(key=lambda i: -i.get("est_tokens", 0))
    auto = sum(i["est_tokens"] for i in items if i.get("tier") == "auto-safe")
    rec = sum(i["est_tokens"] for i in items if i.get("tier") == "recommend")
    loaded = sum(i.get("est_tokens", 0) for i in items)
    return {
        "project_type": ptype, "slug": slug_for(project_path), "items": items,
        "totals": {"est_loaded": loaded, "est_reclaimable_auto": auto, "est_reclaimable_recommend": rec},
        "uncertain": [i["name"] for i in items if i["verdict"] == "uncertain"],
        "second_brain": resolve_second_brain(cfg, home),
    }

def format_text(rep):
    lines = [f"Context Audit (project type: {rep['project_type']}) — token figures are estimates; effect is next-session"]
    t = rep["totals"]
    lines.append(f"  Loaded ~{t['est_loaded']//1000}k est; reclaimable here: ~{t['est_reclaimable_auto']//1000}k auto, ~{t['est_reclaimable_recommend']//1000}k via recommendations.")
    lines.append(f"  {'cat':<8}{'item':<22}{'est':>7}  {'verdict':<10}{'action'}")
    for i in rep["items"]:
        action = i.get("action") or i.get("fix_command") or i["tier"]
        lines.append(f"  {i['category']:<8}{i['name'][:21]:<22}{i.get('est_tokens',0):>7}  {i['verdict']:<10}{action}")
    if not any(i["tier"] in ("auto-safe", "recommend") for i in rep["items"]):
        lines.append("  Nothing material.")
    sb = rep.get("second_brain") or {}
    if sb.get("dispatch_enabled"):
        lines.append(f"  Second_Brain dispatch: enabled ({sb['path']})")
    elif sb.get("configured"):
        lines.append(f"  Second_Brain dispatch: disabled (configured path not found: {sb['configured']})")
    else:
        lines.append("  Second_Brain dispatch: disabled (no path configured)")
    return "\n".join(lines)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Context audit for /sync")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--home", default=os.path.expanduser("~"))
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent / "context-audit.config.json"))
    ap.add_argument("--format", choices=["json", "text"], default="json")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    rep = build_report(Path(args.home), Path(args.project), cfg)
    if args.format == "text":
        print(format_text(rep))
    else:
        print(json.dumps(rep, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
