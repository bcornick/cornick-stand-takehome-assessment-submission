---
name: cross-review
description: Get a second model to review the whole submission, read-only. Runs once, in milestone 6.
---

# Cross-review

1. Produce the diff of the `submission` branch against `main`: `git diff "$(git merge-base HEAD main)"...HEAD` (include `web/`).
2. Run a different model on it, read-only. From Claude Code:

```
codex exec --sandbox read-only "Review the diff of this branch against main for a project whose scope is docs/build_logs/plan.md and whose design is docs/build_logs/design-spec.md. Read both first. Report: (1) behaviour that contradicts the architecture, with file and line; (2) tests that assert mocked behaviour or cannot fail; (3) behaviour with a consequence that has no test, and tests that docs/build_logs/plan.md's test rule excludes; (4) temporal language or missing ABOUTME headers; (5) anything docs/build_logs/plan.md lists as cut, and anything nothing reads. Do not run the full test suite; run a single focused test only to confirm a specific finding. Do not modify files."
```

   From Codex, run the same prompt through `claude -p` with read-only permissions.
3. For each finding: confirm it against the code, then fix it or record why it stands. A finding that questions the architecture goes to Brett.
4. Record the findings and their handling in the milestone's `docs/build_logs/progress.md` entry.

If the other CLI is not installed, use the `reviewer` subagent and say so in the progress entry.
