# /sync Context Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a context-audit pre-run to `/sync` that discovers loaded MCP servers, plugins, hooks, and owned memory for a project, estimates token weight, classifies each as used/unused/uncertain with a value-aware rule, auto-trims only the safe project-scoped items on confirm, and recommends the rest — packaged as a generic, shareable bundle.

**Architecture:** A deterministic Python helper (`lib/context-audit.py`) does discovery + estimation + value-aware classification from config files (zero hardcoded identity or server names; tuning lives in `context-audit.config.json`). `sync.md` runs the helper, applies model judgment only to `uncertain` items, presents a ranked report, and applies safe trims on user confirm.

**Tech Stack:** Python 3 stdlib only (argparse, json, os, re, pathlib), pytest for tests, bash for install/package.

---

## File Structure

- Create: `lib/context-audit.py` — the audit helper (discovery, estimation, classification, CLI). One file, focused.
- Create: `context-audit.config.json` — the single tuning surface (value_earning / domain_signals / infra_never_touch / thresholds).
- Create: `tests/test_context_audit.py` — pytest suite; builds temp config dirs in-test (no committed fixtures).
- Create: `sync.md` — copy of the current `~/.claude/commands/sync.md` with the new Context Audit stage inserted.
- Create: `README.md`, `install.sh` — packaging.
- Modify (at install time only, never by this plan): user's `~/.claude/commands/sync.md`.

`lib/context-audit.py` is imported as a module by the tests (functions are pure and unit-testable) and runs as a CLI via `main()`.

---

## Task 1: Scaffold project + config + pytest sanity

**Files:**
- Create: `lib/__init__.py` (empty, makes `lib` importable)
- Create: `context-audit.config.json`
- Create: `tests/test_context_audit.py`
- Create: `pytest.ini`

- [ ] **Step 1: Create the config file**

`context-audit.config.json`:
```json
{
  "per_tool_tokens": 150,
  "default_tool_count": 25,
  "memory_chars_per_token": 4,
  "min_flag_tokens": 1000,
  "known_tool_counts": {
    "jcodemunch": 80
  },
  "value_earning": {
    "names": ["jcodemunch"],
    "tool_signatures": ["search", "symbol", "context", "outline", "reference", "dependency", "hierarchy", "blast_radius"]
  },
  "infra_never_touch": {
    "names": ["context7"],
    "plugins": ["superpowers"]
  },
  "domain_signals": {
    "posthog": ["dep:posthog", "dep:posthog-js", "dep:posthog-node"],
    "modular9": ["file:.modular9", "dep:modular9"]
  },
  "memory_caps_lines": { "MEMORY.md": 200, "brain.md": 60, "typed": 40 }
}
```

- [ ] **Step 2: Create empty package marker and pytest config**

`lib/__init__.py`: empty file.

`pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 3: Create the test file with one sanity test**

`tests/test_context_audit.py`:
```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_mod():
    spec = importlib.util.spec_from_file_location("context_audit", ROOT / "lib" / "context-audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_module_imports():
    mod = load_mod()
    assert hasattr(mod, "DEFAULTS")
```

- [ ] **Step 4: Create minimal helper so import works**

`lib/context-audit.py`:
```python
#!/usr/bin/env python3
"""Context audit for /sync. See docs/superpowers/specs/2026-05-29-sync-context-audit-design.md."""
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
}
```

- [ ] **Step 5: Run the sanity test**

Run: `cd ~/development/sync-context-audit && python3 -m pytest -q`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add lib context-audit.config.json tests pytest.ini
git commit -m "scaffold: context-audit module, config, pytest"
```

---

## Task 2: Config loader + slug derivation

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_context_audit.py`:
```python
def test_load_config_merges_over_defaults(tmp_path):
    mod = load_mod()
    cfgfile = tmp_path / "c.json"
    cfgfile.write_text('{"per_tool_tokens": 200, "value_earning": {"names": ["foo"]}}')
    cfg = mod.load_config(cfgfile)
    assert cfg["per_tool_tokens"] == 200            # overridden scalar
    assert cfg["value_earning"]["names"] == ["foo"]  # nested dict merged
    assert cfg["value_earning"]["tool_signatures"] == []  # untouched default kept
    assert cfg["default_tool_count"] == 25           # default kept

def test_load_config_none_returns_defaults():
    mod = load_mod()
    cfg = mod.load_config(None)
    assert cfg["memory_chars_per_token"] == 4

def test_slug_for():
    mod = load_mod()
    assert mod.slug_for(Path("/Users/x/dev/Foo")) == "-Users-x-dev-Foo"
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "config or slug"`
Expected: FAIL (AttributeError: no `load_config`).

- [ ] **Step 3: Implement**

Append to `lib/context-audit.py`:
```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest -q -k "config or slug"`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: config loader with nested merge + slug derivation"
```

---

## Task 3: Project-type detection + project signals

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def test_detect_project_type_code_manifest(tmp_path):
    mod = load_mod()
    (tmp_path / "package.json").write_text("{}")
    assert mod.detect_project_type(tmp_path) == "code"

def test_detect_project_type_docs_vault(tmp_path):
    mod = load_mod()
    (tmp_path / "SOUL.md").write_text("# soul")
    assert mod.detect_project_type(tmp_path) == "docs-vault"

def test_detect_project_type_unknown(tmp_path):
    mod = load_mod()
    (tmp_path / "notes.txt").write_text("hi")
    assert mod.detect_project_type(tmp_path) == "unknown"

def test_detect_project_signals_deps_and_files(tmp_path):
    mod = load_mod()
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "1", "posthog-js": "1"}}')
    (tmp_path / "vercel.json").write_text("{}")
    sigs = mod.detect_project_signals(tmp_path)
    assert "dep:next" in sigs
    assert "dep:posthog-js" in sigs
    assert "file:vercel.json" in sigs
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "project_type or signals"`
Expected: FAIL (no `detect_project_type`).

- [ ] **Step 3: Implement**

```python
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
        except Exception:
            pass
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest -q -k "project_type or signals"`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: project-type detection and project signal extraction"
```

---

## Task 4: MCP server discovery + dedupe

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def _write_claude_json(home, data):
    (home / ".claude.json").write_text(__import__("json").dumps(data))

def test_discover_mcp_global_and_project(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; home.mkdir()
    proj = tmp_path / "proj"; proj.mkdir()
    _write_claude_json(home, {
        "mcpServers": {"jcodemunch": {}, "posthog": {}},
        "projects": {str(proj): {"mcpServers": {"localthing": {}}}},
    })
    (proj / ".mcp.json").write_text('{"mcpServers": {"projsrv": {}}}')
    servers = mod.discover_mcp_servers(home, proj)
    by = {s["name"]: s["scope"] for s in servers}
    assert by["jcodemunch"] == "global"
    assert by["posthog"] == "global"
    assert by["localthing"] == "project-user"
    assert by["projsrv"] == "project-mcpjson"

def test_dedupe_servers_prefers_specific_scope():
    mod = load_mod()
    raw = [{"name": "x", "scope": "global"}, {"name": "x", "scope": "project-mcpjson"}]
    out = mod.dedupe_servers(raw)
    assert len(out) == 1 and out[0]["scope"] == "project-mcpjson"
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "mcp or dedupe"`
Expected: FAIL (no `discover_mcp_servers`).

- [ ] **Step 3: Implement**

```python
_SCOPE_RANK = {"global": 0, "project-user": 1, "project-mcpjson": 2}

def load_claude_json(home):
    p = Path(home) / ".claude.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
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
        except Exception:
            pass
    return servers

def dedupe_servers(servers):
    best = {}
    for s in servers:
        cur = best.get(s["name"])
        if cur is None or _SCOPE_RANK[s["scope"]] > _SCOPE_RANK[cur["scope"]]:
            best[s["name"]] = s
    return list(best.values())
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest -q -k "mcp or dedupe"`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: MCP server discovery across global/project scopes with dedupe"
```

---

## Task 5: Plugin, hook, and memory discovery

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def test_discover_plugins(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; (home / ".claude").mkdir(parents=True)
    proj = tmp_path / "proj"; (proj / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text('{"enabledPlugins": ["a@m", "superpowers@m"]}')
    (proj / ".claude" / "settings.json").write_text('{"enabledPlugins": ["b@m"]}')
    names = {p["name"] for p in mod.discover_plugins(home, proj)}
    assert names == {"a@m", "superpowers@m", "b@m"}

def test_discover_hooks(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; (home / ".claude").mkdir(parents=True)
    proj = tmp_path / "proj"; (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": [{"x": 1}, {"y": 2}]}}')
    hooks = mod.discover_hooks(home, proj)
    assert any(h["event"] == "PreToolUse" and h["count"] == 2 for h in hooks)

def test_measure_memory(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"
    proj = tmp_path / "proj"; proj.mkdir()
    slug = mod.slug_for(proj)
    memdir = home / ".claude" / "projects" / slug / "memory"
    memdir.mkdir(parents=True)
    (memdir / "brain.md").write_text("line\n" * 10)
    (memdir / "feedback_x.md").write_text("hello world")
    mem = mod.measure_memory(home, proj)
    files = {f["name"]: f for f in mem["files"]}
    assert files["brain.md"]["lines"] == 11
    assert files["feedback_x.md"]["bytes"] == 11
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "plugins or hooks or memory"`
Expected: FAIL (no `discover_plugins`).

- [ ] **Step 3: Implement**

```python
def settings_files(home, project_path):
    return [
        Path(home) / ".claude" / "settings.json",
        Path(project_path) / ".claude" / "settings.json",
        Path(project_path) / ".claude" / "settings.local.json",
    ]

def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest -q -k "plugins or hooks or memory"`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: plugin, hook, and owned-memory discovery"
```

---

## Task 6: Token estimation helpers

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def test_est_server_tokens_known_and_default():
    mod = load_mod()
    cfg = mod.load_config(None)
    cfg["known_tool_counts"] = {"big": 80}
    est, tc = mod.est_server_tokens("big", cfg)
    assert tc == 80 and est == 80 * 150
    est2, tc2 = mod.est_server_tokens("unknown", cfg)
    assert tc2 == 25 and est2 == 25 * 150

def test_est_memory_tokens():
    mod = load_mod()
    cfg = mod.load_config(None)
    assert mod.est_memory_tokens(400, cfg) == 100
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "est_"`
Expected: FAIL (no `est_server_tokens`).

- [ ] **Step 3: Implement**

```python
def est_server_tokens(name, cfg):
    tc = cfg["known_tool_counts"].get(name, cfg["default_tool_count"])
    return tc * cfg["per_tool_tokens"], tc

def est_memory_tokens(nbytes, cfg):
    return nbytes // cfg["memory_chars_per_token"]
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest -q -k "est_"`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: token estimation helpers (labelled approximate downstream)"
```

---

## Task 7: Value-aware server classification (core)

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def _cfg(mod):
    cfg = mod.load_config(None)
    cfg.update({
        "known_tool_counts": {"jcodemunch": 80, "posthog": 30},
        "value_earning": {"names": ["jcodemunch"], "tool_signatures": ["search", "symbol"]},
        "infra_never_touch": {"names": ["context7"], "plugins": []},
        "domain_signals": {"posthog": ["dep:posthog-js"]},
        "min_flag_tokens": 1000,
    })
    return cfg

def test_classify_value_earning_kept_on_code(mod=None):
    mod = load_mod()
    r = mod.classify_server({"name": "jcodemunch", "scope": "global"}, "code", set(), _cfg(mod))
    assert r["verdict"] == "used" and r["tier"] == "none"

def test_classify_value_earning_flagged_on_vault():
    mod = load_mod()
    r = mod.classify_server({"name": "jcodemunch", "scope": "global"}, "docs-vault", set(), _cfg(mod))
    assert r["verdict"] == "unused" and r["tier"] == "recommend"
    assert "fix_command" in r

def test_classify_infra_never_touched():
    mod = load_mod()
    r = mod.classify_server({"name": "context7", "scope": "global"}, "docs-vault", set(), _cfg(mod))
    assert r["tier"] == "none" and r["verdict"] == "used"

def test_classify_domain_used_when_signal_present():
    mod = load_mod()
    r = mod.classify_server({"name": "posthog", "scope": "global"}, "code", {"dep:posthog-js"}, _cfg(mod))
    assert r["verdict"] == "used"

def test_classify_domain_unused_when_no_signal():
    mod = load_mod()
    r = mod.classify_server({"name": "posthog", "scope": "global"}, "code", set(), _cfg(mod))
    assert r["verdict"] == "unused" and r["tier"] == "recommend"

def test_classify_project_mcpjson_is_auto_safe():
    mod = load_mod()
    r = mod.classify_server({"name": "posthog", "scope": "project-mcpjson"}, "code", set(), _cfg(mod))
    assert r["tier"] == "auto-safe" and "disabledMcpjsonServers" in r["action"]

def test_classify_unknown_is_uncertain():
    mod = load_mod()
    r = mod.classify_server({"name": "mysterymcp", "scope": "global"}, "code", set(), _cfg(mod))
    assert r["verdict"] == "uncertain" and r["tier"] == "none"

def test_classify_below_min_flag_tokens_not_actioned():
    mod = load_mod()
    cfg = _cfg(mod); cfg["min_flag_tokens"] = 1_000_000
    r = mod.classify_server({"name": "posthog", "scope": "project-mcpjson"}, "code", set(), cfg)
    assert r["verdict"] == "unused" and r["tier"] == "none"  # too small to bother
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "classify"`
Expected: FAIL (no `classify_server`).

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest -q -k "classify"`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: value-aware MCP server classification with scope-based action tiers"
```

---

## Task 8: Report assembly + CLI (json/text)

**Files:**
- Modify: `lib/context-audit.py`
- Test: `tests/test_context_audit.py`

- [ ] **Step 1: Write failing tests**

```python
def test_build_report_end_to_end(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; (home / ".claude").mkdir(parents=True)
    proj = tmp_path / "proj"; proj.mkdir()
    (proj / "package.json").write_text('{"dependencies": {"react": "1"}}')  # => code project
    _write_claude_json(home, {"mcpServers": {"jcodemunch": {}, "posthog": {}}})
    cfg = _cfg(mod)
    rep = mod.build_report(home, proj, cfg)
    assert rep["project_type"] == "code"
    names = {i["name"]: i for i in rep["items"]}
    assert names["jcodemunch"]["verdict"] == "used"      # value-earning kept on code
    assert names["posthog"]["verdict"] == "unused"        # domain, no signal
    assert rep["totals"]["est_reclaimable_recommend"] >= names["posthog"]["est_tokens"]
    # items sorted by est_tokens desc
    ests = [i["est_tokens"] for i in rep["items"] if i["category"] == "mcp"]
    assert ests == sorted(ests, reverse=True)

def test_format_text_smoke(tmp_path):
    mod = load_mod()
    rep = {"project_type": "code", "slug": "-x", "items": [
        {"category": "mcp", "name": "posthog", "est_tokens": 4500, "verdict": "unused",
         "tier": "recommend", "reason": "r", "fix_command": "do x"}],
        "totals": {"est_loaded": 4500, "est_reclaimable_auto": 0, "est_reclaimable_recommend": 4500},
        "uncertain": []}
    out = mod.format_text(rep)
    assert "Context Audit" in out and "posthog" in out and "estimate" in out.lower()
```

- [ ] **Step 2: Run to verify fail**

Run: `python3 -m pytest -q -k "build_report or format_text"`
Expected: FAIL (no `build_report`).

- [ ] **Step 3: Implement**

```python
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

def build_report(home, project_path, cfg):
    ptype = detect_project_type(project_path)
    signals = detect_project_signals(project_path)
    servers = dedupe_servers(discover_mcp_servers(home, project_path))
    items = [classify_server(s, ptype, signals, cfg) for s in servers]
    items += _classify_memory(measure_memory(home, project_path), cfg)
    # plugins/hooks: measured + reported only (no auto-action; unreliable/blunt per spec)
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
    return "\n".join(lines)

def main(argv=None):
    ap = argparse.ArgumentParser(description="Context audit for /sync")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--home", default=os.path.expanduser("~"))
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "context-audit.config.json"))
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
```

- [ ] **Step 4: Run to verify pass + full suite**

Run: `python3 -m pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Smoke-run the CLI**

Run: `python3 lib/context-audit.py --project . --format text`
Expected: prints a Context Audit block without error.

- [ ] **Step 6: Commit**

```bash
git add lib/context-audit.py tests/test_context_audit.py
git commit -m "feat: report assembly, memory/plugin/hook items, json+text CLI"
```

---

## Task 9: Insert the Context Audit stage into sync.md

**Files:**
- Create: `sync.md` (copy of current command + new stage)

- [ ] **Step 1: Copy the current command into the project**

Run:
```bash
cp ~/.claude/commands/sync.md ~/development/sync-context-audit/sync.md
```

- [ ] **Step 2: Insert a new "Step 1c: Context audit" subsection**

In `sync.md`, immediately after the Step 1b architecture-detection table (before the `## Artifacts by mode` heading), insert:

```markdown
### Step 1c: Context audit (project mode only)

Before reading project state, run the context-audit helper to see what tooling and memory this project loads and what is wasted here. Helper path (resolve the first that exists): `~/.claude/commands/lib/context-audit.py`.

Run: `python3 ~/.claude/commands/lib/context-audit.py --project "$PWD" --format json`

From the JSON report:
- **uncertain[]**: for each, decide used/unused yourself using project context already in hand (what the repo is, its stack, what this session did). Do not auto-disable an uncertain item; if you judge it clearly unused and heavy, move it to the recommend list, never to auto-action.
- **tier == "auto-safe"** (memory oversize; project `.mcp.json` servers): propose the concrete edit and apply ONLY on user confirm. Memory pruning folds into Step 5 (do not double-write). For a project `.mcp.json` server, add its name to `disabledMcpjsonServers` in the project `.claude/settings.json`.
- **tier == "recommend"** (global/user-scoped servers, plugins): list as one-liners with the provided fix_command. NEVER edit global config (`~/.claude.json`, `~/.claude/settings.json`) or any CLAUDE.md.

Render the audit as the first block of the final report (see Step 7). All token numbers are estimates; state that the effect is next-session. If the helper is missing or errors, skip silently and note one line: "Context audit: helper unavailable."

Skip this step entirely in vault and orchestrator mode.
```

- [ ] **Step 3: Add the audit block to the Step 7 report template**

In `sync.md` Step 7, add above the existing `Sync complete.` block:

```markdown
Context Audit (project type: <type>) — estimates, next-session effect
  Loaded ~<N>k est; reclaimable ~<A>k auto, ~<R>k via recommendations.
  <ranked rows: category · item · est · verdict · applied/recommended/none>
  [recommendations as one-liners with exact commands]
```

- [ ] **Step 4: Add an audit guardrail to the Rules section**

Append to the `## Rules` list in `sync.md`:

```markdown
- **Context audit never touches global config.** It may only edit project `.claude/settings.json` (and only `disabledMcpjsonServers`), and only on confirm. Global MCP servers, user plugins, and CLAUDE.md are recommend-only.
- **Audit estimates are approximate.** Never present them as exact `/context` numbers; always note the effect is next-session.
```

- [ ] **Step 5: Verify the edited command is coherent**

Run: `grep -n "Step 1c" ~/development/sync-context-audit/sync.md`
Expected: matches the inserted heading. Read the surrounding lines to confirm placement is between Step 1b and `## Artifacts by mode`.

- [ ] **Step 6: Commit**

```bash
git add sync.md
git commit -m "feat: wire context-audit stage into sync.md (Step 1c + report + rules)"
```

---

## Task 10: Package (README, install.sh) and build the zip

**Files:**
- Create: `README.md`, `install.sh`

- [ ] **Step 1: Write README.md**

```markdown
# /sync + Context Audit

`/sync` is an architecture-aware project state-sync command for Claude Code. This
bundle adds a **Context Audit** pre-run: before syncing, it discovers the MCP servers,
plugins, hooks, and auto-loaded memory this project pulls into the context window,
estimates their token weight, and flags what is wasted *for this project* — trimming
the safe project-scoped items on your confirm and recommending the rest.

Token figures are estimates (Claude Code's `/context` numbers are not exposed to
commands). MCP/plugin changes take effect on the next session, not the current one.

## Layout
```
sync.md                      the command (install to ~/.claude/commands/)
lib/context-audit.py         the audit helper (install to ~/.claude/commands/lib/)
context-audit.config.json    the tuning surface (install beside the helper)
install.sh                   copies the above into place
```

## Install
```bash
./install.sh
```
Then run `/sync` inside any project.

## Tuning (this is the generic surface)
Edit `context-audit.config.json`:
- `value_earning` — servers that *reduce* consumption (code-intelligence, retrieval).
  Kept on code projects, flagged only where there is no code to analyze. Match by
  `names` or by `tool_signatures` so unknown servers of the same kind are caught too.
- `domain_signals` — server/plugin → project signals (`dep:<pkg>`, `file:<name>`,
  `dir:<name>`, `gitremote:<host>`) that mark it actually used here.
- `infra_never_touch` — servers/plugins never flagged.
- `known_tool_counts` — per-server tool counts for sharper estimates (read them off
  `/context` once). Unknown servers use `default_tool_count`.

Nothing is hardcoded to one machine; the helper derives paths from `$HOME` and the
project path and discovers whatever is configured.
```

- [ ] **Step 2: Write install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD_DIR="$HOME/.claude/commands"
LIB_DIR="$CMD_DIR/lib"
mkdir -p "$LIB_DIR"
cp "$HERE/sync.md" "$CMD_DIR/sync.md"
cp "$HERE/lib/context-audit.py" "$LIB_DIR/context-audit.py"
cp "$HERE/context-audit.config.json" "$LIB_DIR/context-audit.config.json"
chmod +x "$LIB_DIR/context-audit.py"
echo "installed: $CMD_DIR/sync.md"
echo "installed: $LIB_DIR/context-audit.py"
echo "installed: $LIB_DIR/context-audit.config.json"
echo "Run /sync inside any project. Edit the .config.json to tune for your tools."
```

Note: the config installs to `lib/` next to the helper; the helper's `--config`
default resolves to `parent.parent / context-audit.config.json`. Update the helper
default in Task 8 if you change this location. (Verified: with helper at
`~/.claude/commands/lib/context-audit.py`, `parent.parent` is `~/.claude/commands`,
NOT `lib/`. Fix the default to `Path(__file__).resolve().parent / "context-audit.config.json"` so it sits beside the helper in `lib/`.)

- [ ] **Step 3: Apply the config-path fix flagged above**

In `lib/context-audit.py` `main()`, change the `--config` default to:
```python
ap.add_argument("--config", default=str(Path(__file__).resolve().parent / "context-audit.config.json"))
```
And in `install.sh` confirm the config is copied into `$LIB_DIR` (it is). Re-run `python3 -m pytest -q` to confirm nothing broke (tests pass `--config` explicitly, so they are unaffected).

- [ ] **Step 4: Build the zip to the Desktop**

Run:
```bash
cd ~/development && rm -f ~/Desktop/sync-context-audit.zip
zip -r -q ~/Desktop/sync-context-audit.zip sync-context-audit \
  -x 'sync-context-audit/.git/*' 'sync-context-audit/**/__pycache__/*' '*.pyc' '*.DS_Store'
unzip -l ~/Desktop/sync-context-audit.zip
```
Expected: archive lists sync.md, lib/context-audit.py, context-audit.config.json, README.md, install.sh, docs/.

- [ ] **Step 5: Commit**

```bash
git add README.md install.sh lib/context-audit.py
git commit -m "feat: packaging (README, install.sh) and config-path fix"
```

---

## Task 11: Live dry-run verification (no global writes)

**Files:** none (verification only)

- [ ] **Step 1: Run against a real code project**

Run: `python3 ~/development/sync-context-audit/lib/context-audit.py --project ~/development/sync-context-audit --format text`
Expected: project type `code`; if jcodemunch is configured globally it shows verdict `used` (kept), NOT recommended for removal.

- [ ] **Step 2: Run against the Second_Brain vault (non-code)**

Run: `python3 ~/development/sync-context-audit/lib/context-audit.py --project ~/development/Vaults/Second_Brain --format text`
Expected: project type `docs-vault`; jcodemunch (if global) shows verdict `unused`, tier `recommend` with a `claude mcp` fix command. This is the core proof of the value-aware rule.

- [ ] **Step 3: Confirm no global files were modified**

Run: `git -C ~ diff --stat 2>/dev/null; ls -la --time-style=+%s ~/.claude.json ~/.claude/settings.json`
Expected: the helper is read-only; `~/.claude.json` and `~/.claude/settings.json` mtimes unchanged by the audit run. (The helper never writes; only `/sync` writes, and only project files on confirm.)

- [ ] **Step 4: Record the result**

Note in the commit message what the two dry-runs showed (jcodemunch kept on code, flagged on vault).

```bash
git -C ~/development/sync-context-audit commit --allow-empty -m "test: dry-run verified value-aware rule (jcodemunch kept on code, flagged on vault); helper makes no global writes"
```

---

## Self-Review

**Spec coverage:**
- Hard constraints (no /context call, global-undisablable, next-session, estimates) → encoded in Task 7 tiers, Task 8 labels, Task 9 guardrails. ✓
- Two tiers (auto-safe vs recommend) → Task 7 `_flag` + Task 9 handling. ✓
- Discovery of all four categories (MCP/plugins/hooks/memory) → Tasks 4, 5, 8. ✓
- Value-aware classification + project-type detection → Tasks 3, 7. ✓
- Portability / config tuning surface → Task 1 config, Task 10 README. ✓
- Output report block → Task 8 `format_text` + Task 9 report wiring. ✓
- Guardrails (no global/CLAUDE.md writes, confirm-only) → Task 9. ✓
- Testing (fixtures via tmp_path, dry-run on code+vault) → Tasks 2-8, 11. ✓
- Out-of-scope (vault auditing, auto global writes, plugin auto-disable) → respected; plugins/hooks are report-only in Task 8. ✓

**Placeholder scan:** `<type>`/`<N>k` appear only inside the report *template* the model fills at runtime (correct), not as un-implemented code. No TODO/TBD in code steps.

**Type consistency:** report dict keys (`project_type`, `slug`, `items`, `totals{est_loaded,est_reclaimable_auto,est_reclaimable_recommend}`, `uncertain`) are consistent across Task 8 and tests. Item keys (`category`, `name`, `est_tokens`, `verdict`, `tier`, `reason`, optional `action`/`fix_command`/`scope`/`tool_count`) consistent across Tasks 7-8 and `format_text`. `classify_server` signature `(server, project_type, project_signals, cfg)` matches all call sites. Config-path default reconciled in Task 10 Step 3.
