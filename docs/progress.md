# Progress log

One entry per stage or handed-back task, latest last. Format is in `.agents/skills/stage/SKILL.md`.

## Stage 00: design handoff

**Done:** architecture, critique, staged plan with acceptance checks, agent instructions, hooks, skills, Stand's harness and source material copied in unmodified.
**Not done:** no application code exists. Stage 1 starts from an empty `src/`.
**Checks:** `python3 scripts/check_discipline.py` passes on the handoff files. The handoff went through three rounds of four-lens review with a cross-model panel each round; the last round found no blocker.
**Friction:** none recorded.
**Next:** Stage 1, first task. Read `docs/architecture.md` in full before starting. Stage 3 has a human gate: Brett reviews every interpretation row in architecture section 9.7 and signs the ten lead labels.

## Stage 01, task 2: SDK and library verification (stage-01-scaffold-t0)

Checked on 2026-10-05 against DeepSeek's documentation of its Anthropic-format endpoint (https://api-docs.deepseek.com/guides/anthropic_api), the versions pinned in `uv.lock` (anthropic 1.11.0, httpx2 2.13.1, starlette 1.7.0), and live calls to `https://api.deepseek.com/anthropic` with `MODEL_ID` `deepseek-flash`.

1. **Structured output.** DeepSeek's compatibility table lists `tool_choice` as supported for `none`, `auto`, `any` and `tool` (`disable_parallel_tool_use` is ignored), and `tools` with `name`, `description` and `input_schema` as fully supported. It lists `output_config` as "Only `effort` is supported", so the output format that `messages.parse()` sends is not applied; §6.2 stands: structured output is a forced tool call validated with Pydantic, and `messages.parse()` is not used. Confidence: high for the documentation; the live result is finding 2.
2. Forced tool call on deepseek-flash: works with thinking switched off, and only then. A request with `tool_choice={"type": "tool", "name": ...}`, `temperature` 0 and no `thinking` parameter was refused with HTTP 400, `Thinking mode does not support this tool_choice` (request id 445ca0c0-f8e4-4c77-8a37-98a24846e55d). The same request with `thinking={"type": "disabled"}` returned HTTP 200, `stop_reason` `tool_use`, one `tool_use` block for the named tool and no other block (request id 9465903a-5b28-4352-94af-201b32781203). The tool's `input_schema` was the JSON schema of the A.9 `ReplyReading` model, and the tool input passed `ReplyReading.model_validate`: the schema matched. Thinking had to be switched off for the call; DeepSeek's page does not say that thinking is on by default or that it excludes a forced tool choice. Confidence: high (observed).
3. Sampling parameters accepted by deepseek-flash: `temperature` in the range 0.0 to 2.0 ("Fully Supported"); `top_p` "only takes effect in thinking mode (with a lower bound of 0.95); in non-thinking mode it is fixed at 1.0"; `top_k` is ignored. `read_reply` sends `temperature` 0 (A.10). In anthropic 1.11.0, `messages.create()` has no `temperature`, `top_p` or `top_k` argument (`inspect.signature`; passing `temperature=0` raises `TypeError: Messages.create() got an unexpected keyword argument 'temperature'` before any request is sent), so the value goes in `extra_body={"temperature": 0}`, the route the SDK documents. The live call sent it that way and was accepted; one call cannot show that the value is honoured. Confidence: high for acceptance, unknown for effect.
4. **Test client.** Starlette's `TestClient` is an `httpx2.Client`: its MRO is `starlette.testclient.TestClient`, `httpx2.Client`, `httpx2._client.BaseClient`, `object`, and `TestClient(Starlette())` built under `python -W error` with `warnings.catch_warnings(record=True)` recorded no warning. Shown by `uv run python -W error` on the installed starlette 1.7.0 and httpx2 2.13.1. anthropic 1.11.0 itself depends on `httpx2<3,>=2.0.0`, so the app has one HTTP client library. Confidence: high.

Also observed in the live call, outside the four findings: the model returned the right values for the two asks (2019 and 3) with wrong character offsets. Its `span_start`/`span_end` selected " and" and "n" in the reply, not "2019" and "3". One sample, with a prompt written for this check and not the `read_reply` prompt. A.9 and §10.4 step 1 rest on offsets that code verifies against the stored reply, so this is raised with Brett before the stage 2 contract gate.

Other facts from the documentation: an unsupported model name maps to `deepseek-flash`, and names starting `claude-opus` map to `deepseek-v4-pro`, billed at that model's price, so `MODEL_ID` must never be a Claude Opus id on this endpoint. `anthropic-version` and, for `/messages`, `anthropic-beta` are ignored. `cache_control` is ignored. Message content of type `document` is not supported.

Live calls and tokens: two requests. The refused one returned no usage. The accepted one used 575 input and 134 output tokens (709 in total), no cache tokens. The plan names one verification call; the second was made because the task asks whether thinking had to be switched off, which the refused request alone could not answer. No retry loop: the client ran with `max_retries=0`.

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

## Stage 01: model provider change (stage-01-scaffold-t0)

**Done:** Brett approved a design change: the language model is DeepSeek V4.1 Flash (`deepseek-flash`) through DeepSeek's Anthropic-format endpoint with the Anthropic SDK. The design branch `design-model-provider` (tip 3620377: architecture, plan, acceptance checks, `AGENTS.md`, `.env.example`) was fast-forwarded into the stage branch, and its worktree and branch removed. A builder on Sonnet brought the code in line, test first: `Settings` has `model_id` (`MODEL_ID`, default `deepseek-flash`) and `model_base_url` (`MODEL_BASE_URL`, default `https://api.deepseek.com/anthropic`); `compose.yaml` interpolates both so a shell value overrides `.env`. The lead redid task 2 against DeepSeek's documentation with live calls and replaced its record above.

**Not done:** nothing in `src/` builds a model client yet (stage 9). `MODEL_API_KEY` is not a settings field; plan task 5 does not list it. The Stage 1 entry above was written before this change; where it names Claude or Anthropic's API key, this entry and the task 2 record are current.

**Checks:** `make check` clean, 44 fast tests. `make test-slow` passes, 19 tests. All eleven acceptance checks pass on the final tree, run by the lead: S01-A1 to S01-A11, with S01-A9 (seven variables) and S01-A10 (the forced tool call, sampling and `TestClient` records) passing again. No source file, test or configuration file names the Anthropic model variables.

Questions for Brett that the live call raised; none is settled in code:
1. **Thinking must be off for a forced tool choice.** §6.2 and A.10 do not say so. Without `thinking={"type": "disabled"}` the endpoint refuses the call. Proposed: amend §6.2 and A.10 to say every forced-tool call sends thinking disabled.
2. **`temperature` is not an argument of `messages.create()` in anthropic 1.11.0.** A.10 says `read_reply` sends `temperature` 0. The SDK's documented route is `extra_body={"temperature": 0}`; the alternative is an SDK below 1.0. Proposed: `extra_body`, stated in A.10.
3. **Character offsets.** In the one sample the model's values were right and its offsets wrong. A.9 has the model return `span_start` and `span_end`, and §10.4 step 1 checks them against the stored reply. Options: keep A.9 and measure with the real prompt at stage 9; or have the model return the quoted text and let code find its position, which changes A.9 before the stage 2 contract gate freezes it.
4. **Budget.** $5 of DeepSeek credit is the whole project budget. Token usage of every live or record run is recorded here; a single run above about 500,000 tokens is reported to Brett. This entry's live calls: 709 tokens.

**Friction:**
- The lead's instruction to the builder asked for tests asserting the Anthropic model variable is not read. Those tests named a variable the design no longer has, which is history in a test; the lead removed them (three lines) before the commit.
- A script that printed the model's tool input also printed the reply's substring at the returned offsets, which is how the wrong offsets were seen. Worth keeping in the stage 9 recording step.

**Next:** Stage 2, task 1, on `stage-02-contracts-t0`, after Brett's go-ahead and his answers to questions 1 to 3.
