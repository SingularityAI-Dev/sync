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
