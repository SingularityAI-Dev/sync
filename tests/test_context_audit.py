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
