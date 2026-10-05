---
name: stage
description: Execute one milestone of docs/plan.md from start to hand-back. Use when asked to build or continue a milestone.
---

# Milestone

1. Read the latest entry in `docs/progress.md`, then `docs/plan.md` in full, then the architecture sections the milestone touches.
2. Check `git status`. If the tree is dirty, stop and ask Brett. Work on the `submission` branch.
3. Write the milestone's checks into `docs/acceptance.json`: at most three, each a command that proves a "done when" line.
4. Get the thinnest path working end to end, then widen it. Write a test first for behaviour with a consequence; `AGENTS.md` says which tests are not written. Run `make check` before each commit.
5. Where the architecture is silent or disagrees with itself, take the simplest reading that keeps a lead moving safely and record it in one line in `docs/progress.md`. Stop for Brett only when the choice changes what an underwriter or a producer sees, or spends money.
6. When the "done when" lines hold on the running system: run the `verify` skill, have the `reviewer` subagent read the milestone once and report what can be removed, and fix what it finds. `/cross-review` runs once, in milestone 6.
7. Append to `docs/progress.md`:

```
## Milestone N: <name> (<commit>)
**Done:** ...
**Not done:** ...
**Checks:** make check clean; acceptance ids passed: ...
**Decisions:** one line each
**Next:** the first step of the following milestone
```

## Leading a milestone

The session that runs this skill is the lead. The lead reads, decides the order, hands out work and reads every diff.

1. **One writer.** Hand each piece of work to a fresh `builder` subagent, one at a time. Two agents never write to the checkout at once.
2. **The prompt is the builder's whole world.** Say what the lead in front of it needs, name the architecture sections, list the files it may touch, and say what came before and what comes after.
3. **Keep the two authors apart.** Expected answers (the seed-42 labels, reply fixtures, and a skill's `cases/`) are written by a fresh subagent on the lead's own model that does not read the rules code. The builders that write the rules core and `read_reply` do not open `evals/labels/` or the `cases/` folders. A disagreement between a label and the code is raised with Brett, never settled by editing the label.
