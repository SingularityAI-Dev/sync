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
