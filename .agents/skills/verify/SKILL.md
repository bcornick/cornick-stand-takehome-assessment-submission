---
name: verify
description: Prove a milestone is done by running its checks and reading real state. Use before saying work is complete.
---

# Verify

1. Run `make check`. Read all of the output. It must be clean.
2. For the current milestone, open `docs/build_logs/acceptance.json` and run the `command` of each of its checks. Compare the result with its `description`.
3. For anything that touches sending or replies, read the real mailbox (`GET /leads/{id}/emails` on the mailbox service) and the event log. Do not trust the application's own summary.
4. Set `passes` to true only for checks you ran and saw pass.
5. Report: commands run, pass and fail counts, any failure output verbatim, and anything skipped with the reason.

A check that could not be run is reported as not run, never as passing.
