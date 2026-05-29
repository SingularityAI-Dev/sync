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
