# AGENTS.md

A take-home submission for Stand Insurance: a small skill-and-eval harness whose first vertical is underwriting triage. Address the human as **Brett**.

## Authority

- `docs/architecture.md` is the single authority. If code, the plan, or this file disagrees with it, stop and raise it with Brett. Do not resolve it silently.
- `docs/critique.md` is the counterweight. Its findings are dispositioned in architecture section 16.
- `docs/plan.md` gives the stages. Work one stage at a time. `docs/acceptance.json` lists the checks; flip `passes` only after running the command.
- `docs/progress.md` is the log. Read the latest entry before starting. Add an entry when a stage or task ends.

## Hard boundaries

- `sim-harness/` is Stand's code. Never edit it.
- `docs/brief/` and `docs/playbook/` are source material. Never edit them.
- The application never reads the generator's debug answer key. Only `tools/` and `evals/` may run generator code.
- `evals/labels/` is written without reading `src/uwh/rules/`. If you are implementing rules, do not edit labels to make a test pass; raise the disagreement.
- Decision-path rules, thresholds and graders change only by a human-approved commit. Do not weaken a grader, a threshold or a test to get green.
- Never commit `.env` or any key.

## Commands

```
make up          # docker compose up --build
make check       # lint, types, discipline checks, fast tests, frontend checks
make test-slow   # slow and integration tests (containers running)
make eval        # docker compose run --rm eval
```

`make check` must pass with clean output before any task is called done. The Stop hook runs it.

## How to work

1. State the task as objective, constraints, success criteria, verification.
2. Write the failing test first. Run it and see it fail for the right reason.
3. Write the smallest change that passes. Refactor with tests green.
4. Run `make check`. Commit. One task, one commit.
5. If stuck after three attempts at one fix, stop and write up what was tried.

Find the root cause of every failure. No workarounds, no skipped tests, no disabled hooks. Every failing test is yours to fix or to raise.

## Testing rules

- Tests assert real behaviour. No test whose assertion is satisfied by a mock.
- No mocks in end-to-end or integration tests: they run against the real leadgen and mailbox containers.
- Model calls in tests use the replay recordings, never a hand-written fake response.
- Output is pristine: an expected error is captured and asserted.
- Mark tests over 5 seconds `@pytest.mark.slow`; container tests `@pytest.mark.integration`.
- Every `src/uwh/<pkg>/<name>.py` has a `tests/**/test_<name>.py`.
- Never delete a failing test. Raise it.

## Writing rules

- Every code file starts with two comment lines beginning `ABOUTME: ` saying what the file does.
- **No temporal or historical language in any artifact:** code, comments, docs, test names, YAML. Describe what is. History lives in git. `scripts/check_discipline.py` enforces a word list; the rule is wider than the list.
- Names say what a thing does in the domain: `Blocker`, `AskPlan`, `send()`. No implementation details, pattern names or words like "new", "legacy", "wrapper", "improved".
- Comments explain what or why. Keep existing comments unless they are false.
- YAGNI. The runtime gets only what two or more skills need. No flexibility nobody asked for.
- Match the surrounding style. Change only what the task needs.

## Git

- Work on a branch per stage: `stage-NN-short-name`. Brett merges.
- Claude-authored commit subjects start with `CLAUDE-<model-name>: `. Other agents use their own model name the same way.
- Never `git add -A` without a fresh `git status`. Never `--no-verify`.

## Review

- Before a stage is called done, run the `verify` skill, then the `cross-review` skill.
- Reviewers read code and test output. They do not rerun the full suite.

## Friction

When something costs time twice, turn it into a check or a make target. Only if that is impossible, add one line here.
