#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD_DIR="$HOME/.claude/commands"
LIB_DIR="$CMD_DIR/lib"
mkdir -p "$LIB_DIR"
cp "$HERE/sync.md" "$CMD_DIR/sync.md"
cp "$HERE/lib/context-audit.py" "$LIB_DIR/context-audit.py"
cp "$HERE/lib/context-audit.config.json" "$LIB_DIR/context-audit.config.json"
chmod +x "$LIB_DIR/context-audit.py"
echo "installed: $CMD_DIR/sync.md"
echo "installed: $LIB_DIR/context-audit.py"
echo "installed: $LIB_DIR/context-audit.config.json"
echo "Run /sync inside any project. Edit the .config.json to tune for your tools."
