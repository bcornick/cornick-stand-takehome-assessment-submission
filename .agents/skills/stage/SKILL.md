---
name: stage
description: Execute one stage of docs/plan.md from start to hand-back. Use when asked to build or continue a stage.
---

# Stage

1. Read the latest entry in `docs/progress.md`, then the stage section in `docs/plan.md`, then the architecture sections it names.
2. Check `git status`. If the tree is dirty, stop and ask Brett.
3. Create or switch to the stage branch `stage-NN-short-name-tN`, based as `AGENTS.md` says.
4. Work the stage's tasks for the tier being built, in the order the plan gives for that tier pass. Each code task is test-first: failing test, smallest passing change, `make check`, commit. You are the lead for the stage; see "Leading a stage" below for who does the writing.
5. If the stage needs something the architecture does not define, stop. Write the question in `docs/progress.md` and ask Brett. Do not invent it.
6. At a human gate, stop and hand back.
7. When all tasks are done: run the `verify` skill, then the `cross-review` skill, and fix what they find.
8. Update the stage's implemented / not implemented lists if they changed.
9. Append to `docs/progress.md`:

```
## Stage NN: <name> (<branch>, <commit>)
**Done:** ...
**Not done:** ...
**Checks:** make check clean; acceptance ids passed: ...
**Friction:** what cost time; anything seen twice and the check or make target added for it
**Next:** the first task of the following stage
```

## Leading a stage

The session that runs this skill is the lead. The lead reads, decides the order, hands out tasks and checks results. It does not write tests or code itself, except for a stage with three tasks or fewer.

1. **One task, one fresh agent.** Hand each task, or a small group that edits the same files, to a fresh `builder` subagent. In Claude Code the `builder` agent runs on Sonnet. From another tool, use that tool's smaller coding model.
2. **The prompt is the builder's whole world.** Paste the task text from the plan, name the architecture sections it cites, list the files it may touch, and say what came before and what comes after. Do not make it rediscover the plan.
3. **One writer at a time.** Run builders one after another unless the plan marks tasks as safe in parallel and Brett has asked for parallel work.
4. **Check before moving on.** When a builder reports `DONE`, read its diff and its `make check` result yourself, then have the read-only `reviewer` agent check the diff against the architecture. A builder that reports `NEEDS_CONTEXT` or `BLOCKED` gets the missing context or a smaller task; a question about the architecture goes to Brett.
5. **Keep the two authors apart.** The tasks that write expected answers (the stage 3 labels, per-outcome cases, reply fixtures and held-back replies, and any skill's `cases/`) run in a fresh subagent on the lead's own model, with its context discarded afterwards. The builders that write the rules core (stage 6) and `read_reply` (stage 9) are told not to open `evals/labels/` or the `cases/` folders. A disagreement between a label and the code is raised with Brett, never settled by editing the label.
6. **Record it.** The stage's `docs/progress.md` entry names which tasks each builder took and any task that was handed back.
