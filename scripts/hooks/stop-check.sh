#!/usr/bin/env bash
# ABOUTME: Stop hook that runs the project check command before an agent ends its turn.
# ABOUTME: Exits 2 with the failing output so the agent must fix the cause; exits 0 when checks pass.
set -u
input=$(cat)
active=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null)
[ "$active" = "True" ] && exit 0
# Check the tree the agent is working in, which is its own worktree when it runs isolated.
cwd=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd", ""))' 2>/dev/null)
root=""
[ -n "$cwd" ] && [ -d "$cwd" ] && root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)
cd "${root:-$CLAUDE_PROJECT_DIR}" || exit 0
if ! out=$(python3 scripts/check_discipline.py 2>&1); then
  printf 'Discipline check failed. Fix these before stopping:\n%s\n' "$out" >&2
  exit 2
fi
# The hook inherits the PATH of the terminal Claude Code started in, which may hold another Node;
# nvm and the repository's .nvmrc select the Node, and its pnpm, that the web checks need.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ] && [ -f .nvmrc ]; then
  set +u # nvm.sh reads unset variables
  . "$NVM_DIR/nvm.sh"
  nvm use >/dev/null 2>&1
  set -u
fi
if [ -f Makefile ] && grep -q '^check:' Makefile; then
  if ! out=$(make check 2>&1); then
    printf 'make check failed. Fix the cause before stopping:\n%s\n' "$(printf '%s' "$out" | tail -n 60)" >&2
    exit 2
  fi
fi
exit 0
