# Progress log

One entry per stage or handed-back task, latest last. Format is in `.agents/skills/stage/SKILL.md`.

## Stage 00: design handoff

**Done:** architecture, critique, staged plan with acceptance checks, agent instructions, hooks, skills, Stand's harness and source material copied in unmodified.
**Not done:** no application code exists. Stage 1 starts from an empty `src/`.
**Checks:** `python3 scripts/check_discipline.py` passes on the handoff files. The handoff went through three rounds of four-lens review with a cross-model panel each round; the last round found no blocker.
**Friction:** none recorded.
**Next:** Stage 1, first task. Read `docs/architecture.md` in full before starting. Stage 3 has a human gate: Brett reviews every interpretation row in architecture section 9.7 and signs the ten lead labels.

## Stage 01, task 2: SDK and library verification (stage-01-scaffold-t0)

Checked on 2026-10-05 against Anthropic's documentation and the versions pinned in `uv.lock`: anthropic 1.11.0, httpx2 2.13.1, starlette 1.7.0. No live model call was made; the three API findings rest on the documentation and are unverified against the live API until stage 9 records an exchange.

1. **Structured output.** `client.messages.parse(model=..., max_tokens=..., messages=..., output_format=<Pydantic model>)` returns a response whose `parsed_output` is a validated instance of the model. No beta header is needed, and `claude-sonnet-5-5` is on the supported-model list. A `refusal` or `max_tokens` stop reason can leave the output off-schema, so `read_reply` checks `stop_reason` before reading `parsed_output` (A.10 maps `refusal` to the typed abstention). Source: https://platform.claude.com/docs/en/build-with-claude/structured-outputs. The installed SDK agrees: `inspect.signature(Anthropic(api_key="x").messages.parse)` lists `output_format` and `output_config`. Confidence: high.
2. **Forced `tool_choice`.** `claude-sonnet-5-5` rejects `tool_choice` of type `any` or `tool` with a 400, `tool_choice: type "tool" and "any" are not supported for this model.` §6.2 stands: structured outputs are used and forced `tool_choice` is not. Source: https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide, section "Forced tool use is not supported". Confidence: high.
3. Sampling parameters accepted by claude-sonnet-5-5: none at a non-default value. The guide says "On Claude Sonnet 5.5, a non-default value returns a 400 error" for `temperature`, `top_p` and `top_k`. `read_reply` sends none (A.10), and `messages.parse` in anthropic 1.11.0 has no `temperature`, `top_p` or `top_k` argument (same `inspect.signature` call). Source: the same migration guide, section "Migrating to Claude Sonnet 5.5 from Claude Sonnet 4.6 and earlier Sonnet models", Breaking changes. Confidence: high. Consequence for the evals: repeat agreement in the Reply reading grader (§13.3) cannot be bought with temperature 0; it has to come from the prompt and the schema.
4. **Test client.** Starlette's `TestClient` is an `httpx2.Client`: its MRO is `starlette.testclient.TestClient`, `httpx2.Client`, `httpx2._client.BaseClient`, `object`, and `TestClient(Starlette())` built under `python -W error` with `warnings.catch_warnings(record=True)` recorded no warning. Shown by `uv run python -W error` on the installed starlette 1.7.0 and httpx2 2.13.1. anthropic 1.11.0 itself depends on `httpx2<3,>=2.0.0`, so the app has one HTTP client library. Confidence: high.

## Stage 01: Scaffold and harness integration (stage-01-scaffold-t0, c46c0b9)

**Done:** all eight tier-0 tasks. Compose starts Stand's leadgen and mailbox from their unmodified Dockerfiles on 8081 and 8025 and the app on 8000, each with a named volume and a healthcheck. The app image holds the locked dependencies, `src/` without any `cases/` folder, the registry at `/app/registry/field_registry.json`, the `sqlite3` CLI and `GIT_COMMIT`. Settings, the synchronous leadgen and mailbox clients on `httpx2` (no debug method), `GET /api/run` with `run_id` null, `tests/conftest.py`, and the bootstrap with `python -m uwh.runtime.bootstrap`. Tool configuration, the Makefile, the registry copy guard, `.env.example`, `.dockerignore`, and the task 2 record above.

Who did what: builders on Sonnet took task 1; tasks 3 and 4; tasks 5 and 6; tasks 7 and 8; the fixes from the per-task reviews; the fixes from the stage review; and the fixes from the Codex review. The lead did task 2 (documentation checks and the record) and two configuration fixes to `pyproject.toml` after the task 1 review. The reviewer on Opus read each builder's commits. No task was handed back.

**Not done:** nothing of stage 1. Contracts, web, eval services and all runtime and underwriting behaviour are later stages, as the plan lists. The linux/amd64 image build is not run; only arm64 was built (stage 13 runs the platforms).

**Checks:** `make check` clean, 44 fast tests. `make test-slow` passes: 19 tests, 10 against the containers and 9 that build the app image. Acceptance ids passed, each run by the lead on the final tree: S01-A1, A2, A3, A4, A5, A6, A7, A8, A9, A10, A11. First start of all three services from this repository came up healthy with no change to Stand's code (architecture §15 item 1).

Cross-review ran twice. The `codex` CLI first answered "You've hit your usage limit ... try again at 4:52 AM", so the stage diff went to the `reviewer` subagent. Codex then reviewed the same diff once its limit had reset.

Codex (gpt-6-astra, read-only, no tests run) found no contradiction with the architecture, no mocked or unfalsifiable test and nothing outside the stage. Its findings and their handling:
- The image's guarantees had no automated check: `tests/packaging/test_image.py` (slow) builds the `app` target from a temporary context holding a sentinel `cases/` folder and an `evals/` file, and asserts no `cases/` in the tree or in any layer, no `evals/`, the registry byte for byte, `GIT_COMMIT` with and without the build argument, the interpreter and `sqlite3`. Removing the `cases/` deletion, the registry copy or the `GIT_COMMIT` line from the `Dockerfile` each fails it.
- No test could tell whether `post_queue` sends `count`: an integration test posts a queue of three.
- The two empty `__init__.py` files had no `ABOUTME:` lines; the script exempts them and the written rule does not: added.

The `reviewer` subagent's findings and their handling:
- `AttributeError` among the bootstrap's caught errors could report a defect in this code as an invalid environment: removed.
- Five bootstrap checks had no test, and `leads_read` could pass without `get_lead` being called: one fast test per check, each shown to fail when its check is removed.
- One test relied on the order of the leadgen and mailbox checks; one assertion could not fail: both fixed.
- No contradiction with the architecture; nothing under `sim-harness/`, `docs/brief/` or `docs/playbook/` changed; the task 2 record matches the installed versions. The Anthropic pages behind that record were not re-read by the reviewer.

Per-task review findings that were fixed: the compose test pins the default-profile services (so the eval profile can be added in stage 5) and the full healthcheck commands; `conftest.py` asserts the standard-library `mailbox` is not loaded where it used to unload it; the bootstrap maps a non-JSON answer, a wrong-shaped answer and a malformed URL to `EnvironmentInvalid` (§13.1); a seed-11 bootstrap test and an environment-path test for the app factory separate right from wrong where the defaults could not.

Decisions made in the stage, for Brett to confirm or change:
1. `UWH_DB` has no default anywhere in the plan or the architecture. `Settings.load()` requires it and raises a `ValueError` naming it. Compose sets it; tests that build settings pass a placeholder path.
2. The plan gives ruff `extend-exclude = ["sim-harness"]`. That alone fails `ruff format --check .`, because ruff 0.16.10 formats Python blocks inside Markdown and wants to reformat the A.9 block in `docs/architecture.md`. `pyproject.toml` keeps the plan's `extend-exclude` and adds `[tool.ruff.format] exclude = ["*.md"]`. Plan task 1 does not mention this.
3. The app is built by a factory: `create_app(settings=None)`, started with `uvicorn --factory uwh.api.app:create_app`. Nothing reads the environment at import, and the eval runner can pass its own settings (§13.1).
4. `tests/runtime/test_bootstrap.py` uses standard-library HTTP servers on localhost as a wrong service at the configured URL (HTML, wrong-shaped JSON, or leadgen-shaped answers with one wrong answer). The assertions are on the bootstrap's own error, never on the server's answer. Lead and reviewer both read this as inside the AGENTS.md mock rules; Brett has the final say.
5. Configuration files: `Dockerfile`, `Makefile` and `compose.yaml` carry the two `ABOUTME:` lines; `pyproject.toml`, `.env.example` and `.dockerignore` do not. The discipline script checks only `.py`, `.ts`, `.tsx` and `.sh`.
6. The bootstrap summary carries `bootstrap_id` and `leads_read` beside the `lead_ids` and `probe` keys S01-A2 reads. The probe goes from and to `uw@stand.com` (A.8 gives the sender; nothing names a recipient for the probe).

Known gaps, recorded and not fixed:
- `hatchling` is not version-pinned in `[build-system]`, so the image build takes the current release.
- S01-A4 prints `DEBUG` and does not assert it; with `DEBUG=true` in `.env` it would print `true` and still exit 0.
- The bootstrap probe stays in the mailbox under `BOOTSTRAP-<id>`. Stage 5 graders must ignore those lead ids or reset the eval mailbox after the bootstrap.
- `UWH_DB` follows the shell's `RUN_MODE` through compose interpolation, so `docker compose run -e RUN_MODE=replay` would open the live database. The record and replay make targets (stages 9 and 13) must set `RUN_MODE` in the shell.
- `make eval` stamps `git rev-parse HEAD` while building from the working tree, so a dirty tree gets a commit that is not the code it ran. A question for stage 5.

**Friction:**
- `codex exec` waits on stdin when run without a terminal ("Reading additional input from stdin...") and hangs. It needs `< /dev/null`; the cross-review skill's command does not have it. Seen once; if it recurs, the skill's command gets the redirect.
- The integration test that posts three leads leaves the leadgen container's queue at three. Every test and the bootstrap post their own queue, so nothing depends on it, but a person reading `GET /leads` by hand after `make test-slow` sees three leads until the next bootstrap or run start.
- A shell loop that prints `${PIPESTATUS[0]}` prints nothing under zsh, so the first acceptance pass showed outputs without exit codes and had to be rerun with `bash -c "$cmd"; echo $?`.
- A regular expression used to set `passes` stopped at the first `}` inside S01-A1's command (`{{.Service}}`) and left one entry unmarked; a count of passing ids caught it.
- `ruff format --check <file>` on a named file ignores `format.exclude`; only the directory form used by `make check` honours it.

**Next:** Stage 2, task 1 (vertical registration), on `stage-02-contracts-t0`, after Brett's go-ahead. Stage 2 needs the pnpm 12.9.1 pin in `web/package.json` and a corepack that can launch it in the Dockerfile's frontend stage, and ends at the contract gate.
