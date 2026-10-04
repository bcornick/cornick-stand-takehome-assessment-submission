#!/usr/bin/env bash
# ABOUTME: PostToolUse hook that formats the file an agent just edited.
# ABOUTME: Formats Python with ruff and web sources with prettier when those tools are installed.
set -u
input=$(cat)
file=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
[ -n "$file" ] && [ -f "$file" ] || exit 0
case "$file" in
  */sim-harness/*|*/docs/brief/*|*/docs/playbook/*) exit 0 ;;
  *.py)
    if command -v uv >/dev/null 2>&1 && [ -f "$CLAUDE_PROJECT_DIR/pyproject.toml" ]; then
      (cd "$CLAUDE_PROJECT_DIR" && uv run --quiet ruff format "$file" >/dev/null 2>&1 && uv run --quiet ruff check --fix --quiet "$file" >/dev/null 2>&1) || true
    fi ;;
  *.ts|*.tsx|*.css|*.json)
    if [ -x "$CLAUDE_PROJECT_DIR/web/node_modules/.bin/prettier" ]; then
      "$CLAUDE_PROJECT_DIR/web/node_modules/.bin/prettier" --write "$file" >/dev/null 2>&1 || true
    fi ;;
esac
exit 0
