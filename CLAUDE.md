@AGENTS.md

## Claude Code only

- Skills live in `.agents/skills/` and are linked into `.claude/skills/`: `/verify`, `/stage`, `/cross-review`.
- The `reviewer` subagent is read-only. Use it for a second look at a diff before `/cross-review`.
- Hooks: a format hook runs after each edit; the Stop hook runs the discipline check and `make check` on every stop and blocks on failure. Fix the cause; do not bypass the hook.
- Track multi-step work with the todo list. Do not drop a task from it without Brett's approval.
- Use the memory system only for facts that outlive this repository's sessions. Project state belongs in `docs/progress.md`.
- This repository stands alone. Instruction files from other projects on this machine do not apply here.
