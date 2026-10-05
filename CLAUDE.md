@AGENTS.md

## Claude Code only

- Skills live in `.agents/skills/` and are linked into `.claude/skills/`: `/verify`, `/stage`, `/cross-review`.
- `/stage` makes this session the lead for a milestone: `builder` subagents (Sonnet) write the tests and code one piece of work at a time, the lead reads every diff, and the read-only `reviewer` subagent (Opus) reads the milestone once at its end. `/cross-review` runs once, in milestone 6.
- Hooks: a format hook runs after each edit; the Stop hook runs the discipline check and `make check` on every stop and blocks once on failure; the `verify` skill is the gate for calling work done. Fix the cause; do not bypass the hook.
- Track multi-step work with the todo list. Do not drop a task from it without Brett's approval.
- Use the memory system only for facts that outlive this repository's sessions. Project state belongs in `docs/progress.md`.
- This repository stands alone. Instruction files from other projects on this machine do not apply here.
