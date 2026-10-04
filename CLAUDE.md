@AGENTS.md

## Claude Code only

- Skills live in `.agents/skills/` and are linked into `.claude/skills/`: `/verify`, `/stage`, `/cross-review`.
- The `reviewer` subagent is read-only. Use it for a second look at a diff before `/cross-review`.
- Hooks: a format hook runs after each edit; the Stop hook runs `make check` and blocks on failure. Fix the cause; do not bypass the hook.
- This repository stands alone. Instruction files from other projects on this machine do not apply here.
