---
name: cross-review
description: Get a second model to review the stage diff, read-only. Use after verify and before calling a stage done.
---

# Cross-review

1. Produce the diff: `git diff main...HEAD` (include `web/`).
2. Run a different model on it, read-only. From Claude Code:

```
codex exec --sandbox read-only "Review the diff of this branch against main for a project whose authority is docs/architecture.md. Read docs/architecture.md and the stage section of docs/plan.md first. Report: (1) behaviour that contradicts the architecture, with file and line; (2) tests that assert mocked behaviour or cannot fail; (3) missing tests for stated acceptance checks; (4) temporal language or missing ABOUTME headers; (5) anything outside the stage's scope. Do not run the full test suite; run a single focused test only to confirm a specific finding. Do not modify files."
```

   From Codex, run the same prompt through `claude -p` with read-only permissions.
3. For each finding: confirm it against the code, then fix it or record why it stands. A finding that questions the architecture goes to Brett.
4. Record the findings and their handling in the stage's `docs/progress.md` entry.

If the other CLI is not installed, use the `reviewer` subagent and say so in the progress entry.
