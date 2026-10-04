---
name: stage
description: Execute one stage of docs/plan.md from start to hand-back. Use when asked to build or continue a stage.
---

# Stage

1. Read the latest entry in `docs/progress.md`, then the stage section in `docs/plan.md`, then the architecture sections it names.
2. Check `git status`. If the tree is dirty, stop and ask Brett.
3. Create or switch to the stage branch `stage-NN-short-name`.
4. Work the tasks in order. Each code task is test-first: failing test, smallest passing change, `make check`, commit.
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
