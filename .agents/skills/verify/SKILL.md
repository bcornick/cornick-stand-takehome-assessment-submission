---
name: verify
description: Prove a task or stage is done by running its checks and reading real state. Use before saying work is complete.
---

# Verify

1. Run `make check`. Read all of the output. It must be clean.
2. For the current stage, open `docs/acceptance.json` and run the `command` of each check in the tier being built (the tier is the first words of the description). Compare the result with its `description`. Checks of a higher tier are reported as not in scope.
3. For anything that touches sending or replies, read the real mailbox (`GET /leads/{id}/emails` on the mailbox service) and the event log. Do not trust the application's own summary.
4. Set `passes` to true only for checks you ran and saw pass.
5. Report: commands run, pass and fail counts, any failure output verbatim, and anything skipped with the reason.

A check that could not be run is reported as not run, never as passing.
