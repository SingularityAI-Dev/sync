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

def test_classify_value_earning_kept_on_code():
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
    assert r["verdict"] == "unused" and r["tier"] == "none"


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


def test_detect_project_type_code_by_extension(tmp_path):
    mod = load_mod()
    for i in range(3):
        (tmp_path / f"mod{i}.py").write_text("x = 1\n")
    assert mod.detect_project_type(tmp_path) == "code"

def test_detect_project_type_empty_dir_is_unknown(tmp_path):
    mod = load_mod()
    # md > 0 guard must prevent an empty dir being miscalled docs-vault
    assert mod.detect_project_type(tmp_path) == "unknown"

def test_classify_memory_oversized_is_auto_safe():
    mod = load_mod()
    cfg = mod.load_config(None)  # caps: MEMORY.md 200, brain.md 60, typed 40
    mem = {"dir": "/x", "files": [
        {"name": "brain.md", "bytes": 4000, "lines": 90},        # over 60 cap
        {"name": "feedback_a.md", "bytes": 400, "lines": 10},    # typed, under 40
    ]}
    items = mod._classify_memory(mem, cfg)
    by = {i["name"]: i for i in items}
    assert by["brain.md"]["verdict"] == "oversized" and by["brain.md"]["tier"] == "auto-safe"
    assert "action" in by["brain.md"]
    assert by["feedback_a.md"]["verdict"] == "ok" and by["feedback_a.md"]["tier"] == "none"

def test_build_report_includes_oversized_memory_in_auto_total(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; (home / ".claude").mkdir(parents=True)
    proj = tmp_path / "proj"; proj.mkdir()
    slug = mod.slug_for(proj)
    memdir = home / ".claude" / "projects" / slug / "memory"
    memdir.mkdir(parents=True)
    (memdir / "brain.md").write_text("line\n" * 90)  # 91 lines > 60 cap
    rep = mod.build_report(home, proj, mod.load_config(None))
    mem_item = next(i for i in rep["items"] if i["name"] == "brain.md")
    assert mem_item["tier"] == "auto-safe"
    assert rep["totals"]["est_reclaimable_auto"] >= mem_item["est_tokens"]


def test_resolve_second_brain_disabled_when_missing(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; home.mkdir()
    cfg = mod.load_config(None)  # default path "~/development/Vaults/Second_Brain"
    sb = mod.resolve_second_brain(cfg, home)
    # ~ expands against the given home, which has no such dir -> dispatch off
    assert sb["path"].endswith("/development/Vaults/Second_Brain")
    assert sb["exists"] is False and sb["dispatch_enabled"] is False

def test_resolve_second_brain_enabled_when_dir_exists(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"
    (home / "development" / "Vaults" / "Second_Brain").mkdir(parents=True)
    sb = mod.resolve_second_brain(mod.load_config(None), home)
    assert sb["exists"] is True and sb["dispatch_enabled"] is True

def test_resolve_second_brain_custom_path_via_config(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; home.mkdir()
    vault = tmp_path / "elsewhere" / "MyBrain"; vault.mkdir(parents=True)
    cfg = mod.load_config(None); cfg["second_brain_path"] = str(vault)
    sb = mod.resolve_second_brain(cfg, home)
    assert sb["path"] == str(vault)
    assert sb["dispatch_enabled"] is True

def test_resolve_second_brain_blank_disables(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; (home / "development").mkdir(parents=True)
    cfg = mod.load_config(None); cfg["second_brain_path"] = ""
    sb = mod.resolve_second_brain(cfg, home)
    assert sb["configured"] == "" and sb["path"] is None
    assert sb["dispatch_enabled"] is False

def test_build_report_includes_second_brain_block(tmp_path):
    mod = load_mod()
    home = tmp_path / "home"; (home / ".claude").mkdir(parents=True)
    proj = tmp_path / "proj"; proj.mkdir()
    rep = mod.build_report(home, proj, mod.load_config(None))
    assert "second_brain" in rep
    assert set(rep["second_brain"]) == {"configured", "path", "exists", "dispatch_enabled"}
