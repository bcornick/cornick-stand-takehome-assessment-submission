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

## Stage 01: amendments from the live call (stage-01-scaffold-t0)

**Done:** Brett ruled on the three questions of the model provider entry, and the architecture and plan are amended in one commit.
1. **Thinking.** §6.2 and A.10 say every forced-tool call sends `thinking` disabled. The reason is the endpoint's answer to a forced tool choice without it: HTTP 400, `Thinking mode does not support this tool_choice`.
2. **Temperature.** anthropic stays on 1.x. A.10 says `temperature` 0 goes in the call's `extra_body`. One call cannot show that the value takes effect; the three-repeat agreement check of the Reply reading grader at stage 9 is where that is found out.
3. **Offsets.** A.9: the model returns a `quote` for each candidate and no offsets. Code finds the quote in the reply body. A quote that is not found verbatim drops the candidate and the drop is recorded on the `reply_read` event; a quote that occurs more than once takes the first occurrence; the stored output holds `LocatedCandidate`s with `span_start` and `span_end` computed by code. §10.4 step 1, plan stage 2 task 5, stage 3 task 7 and stage 9 tasks 2 and 3 follow. Stage 9 task 2 gains `test_candidate_with_unfound_quote_is_dropped`.

Two edits in that commit go beyond Brett's wording and are for him to confirm at the stage 2 gate, where the diff is shown with the data shapes:
- A.9 says the quote is not empty. An empty string occurs in every body, so without this an empty quote would always be "found".
- §14 said Stage 1 checks "the forced-`tool_choice` restriction against the SDK documentation", a sentence left from the Claude design. It says what stage 1 does under the DeepSeek design.

No acceptance check mentions offsets, thinking or the temperature route, so `docs/acceptance.json` is unchanged.

Jev: Brett added `TYPESAFE_API_KEY` to `.env` with $5 of credit, for stage 12 only. No Jev call is made before the Jev adapter task. Nothing in `src/` reads the variable; if its presence changes behaviour or a skill status before stage 12, work stops and Brett is told.

**Next:** Stage 2, task 1, on `stage-02-contracts-t0`. Brett gave the go-ahead; the stage ends at his review of the data shapes.

## Stage 02: Contracts and thin slice (stage-02-contracts-t0, fcdd9ee) — at the contract gate, not approved

**Done:** tasks 1 to 10 of the tier-0 pass. Vertical registration; the ten A.1 tables with value-set checks and three append-only triggers on `events`; the 28 A.2 event payload models; A.4 hashes and the skill digest; domain models, the provider result and the seven skill contracts, with A.9 as amended (the model returns a `quote`, code computes offsets); the web package (Vite 8.3.2, React 19.3.0, TypeScript 6.0.3, Tailwind 4.3.3, shadcn/ui on Base UI, openapi-typescript 7.13.0, vitest 5.0.3); the 14 A.5 routes declared, every route but `GET /api/run` answering 501; `web/src/api/openapi.json` and the generated `types.ts`; UI fixtures for the ten seed-42 leads and the stand-in API; the queue page and detail pane; the frontend built in the image and served at `/`.

Who did what: builders on Sonnet took tasks 1 and 2; 3 and 4; 5; 6; 7; 8; 9; 10; and five rounds of review fixes. The reviewer on Opus read tasks 1-2, 3-4, 5, 7 with the first two fix rounds, and 8-10 with the third. Codex (gpt-6-astra, read-only) reviewed the stage diff. The lead wrote no code. The last two fix rounds (46a70e6, d93dd2b, 085a045 and 1469e6a, fcdd9ee) were read by the lead and verified by the checks below, and were not sent to a reviewer.

**Not done:** task 11, the human gate. S02-A8 fails until Brett's approval is recorded as `Contracts approved by Brett at <commit>`. Stages 3, 4 and 10 wait on it.

**Checks:** run by the lead on the final tree. `make check` clean: 696 fast Python tests, `tsc -b`, 51 web tests. `make test-slow`: 21 pass. Acceptance ids passed: S02-A1, A2, A3, A4, A5, A6, A7. S02-A8 not passed (the gate). The stage 1 checks S01-A2 to A6 and A9 to A11 still pass; all three containers healthy.

pnpm in the image: the frontend stage is `node:22.23.3-slim`, which bundles corepack 0.36.0, so no corepack install is needed. `docker build --target frontend -t uwh-frontend-probe .` then `docker run --rm -w /app/web uwh-frontend-probe pnpm --version` printed `12.9.1`. Tags probed for their bundled corepack: 22.21.1-slim 0.34.0, 22.22.0-slim 0.34.0, 22.23.0-slim 0.34.6. The pnpm 12 launch on 0.34 was not tried, so that failure is avoided, not reproduced. The image tag publishes linux/amd64 and linux/arm64; only arm64 was built. `web/package.json` pins `"packageManager": "pnpm@12.9.1"` and `engines.node` `>=22 <23`.

Cross-review (Codex) findings and handling: `INSERT OR REPLACE` could overwrite an event (fixed with a third trigger, shown failing first); lead 000's decline notice was round 1 where §7.5 says 0 (fixture and test fixed); a plan-hash assertion compared a function with itself and the six-count summary test could not catch swapped counts (both rewritten and shown to fail); `web/index.html` and `web/src/index.css` had no `ABOUTME` lines (added). Two of its findings are questions 3 and 4 below. It found no mocked test and nothing outside the stage.

### For Brett at the gate

Read: `src/uwh/runtime/event_types.py`, `src/uwh/api/views.py` with `web/src/api/openapi.json`, `src/uwh/skills/contracts.py`, `src/uwh/rules/models.py`, `src/uwh/skills/vertical.py`. The A.9, §6.2, §10.4, §14 and A.10 amendments are commit d9c78fa. To see the pages: `uv run python tools/standin_api.py --port 8765` and `UWH_API_URL=http://localhost:8765 pnpm --dir web dev`.

Where the architecture disagrees with itself or with the plan (each needs a ruling):
1. **Approving a held draft.** A.11 says `artifact_hash` "is omitted for other item kinds", and a draft held by the stop is a `review` item; §7.4 and plan stage 4 task 11 require the hash on that approval. Built: `ApprovePayload.artifact_hash` optional, and the blocker view carries `held_draft_payload_hash` for the two held-draft causes.
2. **Vocabulary in the runtime.** §7 says the runtime holds no insurance vocabulary and stage 4 runs a toy vertical with no edit under `src/uwh/runtime/`. §7.1 lists `delivery_unknown`, `underwriter_review` and `data` as vertical-supplied blocker kinds, while §7.5, §7.4 and §8 have the runtime open them. A.1 fixes blocker owners (`underwriter`, `producer`, `data_team`), the item kind `no_contact_route` and the observation source `underwriter` in tables the runtime owns. Built: the store takes the message kinds from the vertical and fixes the other A.1 sets itself. Options: the vertical registers blocker kinds by role; or those three kinds are runtime kinds.
3. **I56's duration.** `duration_of_non_occupancy` applies to the occupancy modifications, which include a surcharge and coverage changes; §9.6 gives a deadline only to `requirement`. Built: as §9.6. Proposed: an optional deadline on `surcharge` and `coverage_adjustment`.
4. **Hash exclusions.** A.4 hashes every file and excludes only compiled files. Built: hidden files and directories, `*~` and `*.swp` are also skipped, so a stray `.DS_Store` cannot change a digest. Either A.4 is amended or the exclusion is narrowed or removed.
5. **`routine` or `routine_request`.** §10.1 sets `confirmation_only_class` to `routine`; A.1's intent kind and `PlanAsksResult.message_class` say `routine_request`. Built: both, unreconciled.
6. **Edited drafts.** §10.1 makes "any draft a person has edited" a sensitive request. Does `edit_draft` change `intents.kind`? `DraftEdited` carries no kind.

Shapes proposed where the architecture is open (confirm or change):
7. `plan_asks`: the result always holds the outstanding asks, with `request` one of `send`, `none`, `request_open`, `round_limit`; the input carries `requests_sent` and `open_request`. Plan stage 8 tests the round rules on `plan_asks`; the alternative is to keep them in the workflow.
8. `read_reply`: the skill result carries `dropped` beside the located candidates (A.9 calls the stored output "the classification with the located candidates"). How an abstention is recorded on the event log is not settled. `Abstention.reason` is a free string; A.10's two codes are in its docstring.
9. `resolve_data` takes provider results as input: the runtime makes the lookups and the skill stays pure, which reverses the §6 diagram's edge from skills to providers.
10. Rule traces: a trace is a path or a set of alternatives, never both; each alternative holds a list of assumptions, root to leaf; a trace names the choices answered on its path; the plan carries `underwriter_decline` for `decline_lead`, and `proposed_decline` is validated against the declines present. An effect with no board path is not representable.
11. Quote packet: `notes` (not-evaluated pages, §4.1) and `obligations` were added; §10.5's list has neither.
12. Events over the API carry the payload as a JSON object validated against its type's model, not as a typed union, so `openapi.json` does not show the 28 payload shapes; `event_types.py` does.
13. Queue and summary: "follow-ups sent" counts requests of round 2 or later in the fixtures (nine first requests read as 0 follow-ups); "waiting on data" counts every lead waiting on data or the producer; a lead's group follows its highest-priority blocker's owner.
14. `propose_command` may carry any of the other twelve commands, `approve` and `reject` included (§7.4: the assistant "cannot approve"; A.11: the underwriter applies a proposal by submitting it).
15. Numbers: `SurchargeEffect.percent` is a strict integer; `1` and `1.0` hash differently; the plan hash is taken over the plan model's JSON dump.
16. No event records round closure or the move to `dispatching`.
17. The lead detail holds no ask list and no triage, so asks show only in the draft body and blocked fields only as what a page waits on.
18. Who checks `build_quote_packet`'s precondition (§9.6), the skill or the workflow; and whether effects deduplicate by rule id alone or by type and rule id.
19. In commit d9c78fa, two edits beyond Brett's wording: A.9 says the quote is not empty; §14's sentence on what stage 1 checks describes the DeepSeek check.
20. Fixtures: the three always-required fire fields (`distance_to_fire_department`, `fire_department_type`, `dist_to_nearest_fire_hydrant`) are asked where missing; only the four fields conditional on protection class 9 or 10 are blocked. That is the registry reading and matches §5's "four protection-class questions".

Open from stage 1, unanswered: `UWH_DB` required with no default; ruff skipping Markdown in `format`; the app factory; local HTTP servers in fast bootstrap tests; `ABOUTME` lines on `pyproject.toml`, `.env.example` and `.dockerignore`.

Known gaps, recorded and not fixed: the fixtures show no `assumed` fact and no page that declines on every branch (no seed-42 lead produces either on a first pass; tests build them on clones); derived roof and siding classes are missing on several fixture leads; `make check` does not catch `types.ts` drift, only S02-A3 does; an unknown POST under `/api` answers 405 from the static mount, a GET 404; `/mcp` must be mounted inside the factory before the static mount (stage 11); the digest treats every directory under `skills/` as a skill (stage 4 has the skill list); `QueueGroup` has no group for a lead with no open blocker mid-run; the queue tables have no accessible name.

**Friction:**
- Every set of proposed shapes failed its first review on fit, not on style: the models could not represent a case the architecture names (a `decline_lead` ruling, nested alternatives, a pending observation in the detail pane, the round rules). Working each acceptance case of §9.6 and each row of A.11 through the models by hand, before building on them, is what found these. Task 10 was built before tasks 8 and 9 for that reason: it does not depend on the route shapes.
- The first fixtures were written from §5 by description and contradicted §9.4 and §9.6 in several places. Reading the real seed-42 payloads from the leadgen container and deriving each lookup's status from the §9.4 table fixed them.
- Commit 1469e6a alone fails four web tests, because the fixtures changed in it and the web tests in the next commit; `make check` is clean at fcdd9ee.
- The Stop hook ran `make check` while a builder was mid-task with a failing test written first, and reported the failure; the tree belonged to the builder.
- `codex exec` needs `< /dev/null`; with it the stage 2 review ran to completion.

**Next:** Brett's review of the data shapes (task 11). After his approval is recorded, stage 3 task 1 on `stage-03-labels-t0` and stage 4 on `stage-04-runtime-t0`.

## Stage 02: gate rulings and the simplification round (stage-02-contracts-t0)

**Done:** Brett ruled on the gate questions in three rounds; the architecture, plan and code follow.
- Held-draft approvals carry the draft's payload hash (A.11). Surcharges and coverage adjustments may carry a deadline (§9.6, I56). One name, `routine_request`, for the confirmation-only class (§10.1). An edited `routine_request` becomes a `sensitive_request` and `draft_edited` carries the resulting kind (§7.5, A.2). The abstention reason is a closed set of two codes, recorded on `reply_read` (§10.4, A.10). Seven summary counts: every request sent is a follow-up, and each lead counts once among the four waiting counts by its primary next action (§11). A proposal never carries `approve`, `reject` or `propose_command` (§7.4, A.11). Effects deduplicate by type and rule id, the interpreter keeps the committed copy, and the loader refuses an outcome that repeats a type under one rule id (§9.6). The workflow checks `build_quote_packet`'s precondition and the skill refuses an input that breaks it. Round state lives in the reply-wait blocker (A.2). The A.4 hash exclusions name hidden files, `*~` and `*.swp`.
- The generic-engine promise is dropped: the runtime uses underwriting names directly (§7). A role registration built for an earlier ruling was removed with its tests, as was the `Vocabulary` marker in the API views. Each value set is one `Literal` in `src/uwh/runtime/event_types.py`; the run mode is in `settings.py`. Plan stage 4 lost task 13 (the second vertical) and that half of S04-A10. No other stage 4 task exists only to prove the runtime is generic.
- Shapes: a blocker's item kind and cause live in its `detail` only (`BlockerView.item_kind` and `review_cause` removed; the web code read neither). `provider_called` nests the provider result, defined once in `src/uwh/providers/models.py`.
- Simplification round: one strict base model, request kinds defined once, the blocker priority order and the persisting review causes derived from their literals, `CommandClass.human_only` removed, one check that a decline on every branch carries alternatives, duplicate tests removed, and unused web code removed (`button.tsx`, `lib/utils.ts`, `lucide-react`, unused theme variables and exports; built CSS 32,888 to 27,116 bytes with every class the two views render kept).
- `AGENTS.md` carries the clean-code rule and the reviewer's end-of-stage simplification pass. `make check` also runs two drift checks on `web/src/api/openapi.json` and `types.ts` (about one second together).
- Stage 1 points approved by Brett: `UWH_DB` required with no default, ruff skipping Markdown in `format`, local HTTP servers in the bootstrap tests. The app factory is treated as approved (named in one copy of his message and not the other; he has been told). `pyproject.toml`, `.dockerignore` and `.env.example` carry `ABOUTME` lines.

**Unread until a later task.** Each stays because the plan names its reader; any still unread when that task is done is removed then.

| Item | Read from |
|---|---|
| `vertical.TRANSITIONS`, `TERMINAL_STATUSES`, `BLOCKER_KINDS_BY_PRIORITY` | stage 4 task 4 (workflow and waits) |
| `vertical.COMMAND_CLASSES` (nothing in `src/` reads it; tests tie the API's class-name literals to it) | stage 4 task 6 (command layer) |
| `vertical.REFERENCE_MORNING` | stage 4 task 2 (clock) |
| `vertical.CONFIRMATION_ONLY_CLASS` | stage 8 task 1 (`plan_asks`) |
| `Settings.db_path` | stage 4, where the app first opens the store (the task text does not name `UWH_DB`; unverified which task) |
| `Settings.git_commit` | stage 5 task 3 (results log) |
| `Settings.registry_path` | stage 6 task 1 (registry loader) |
| `Settings.model_id`, `Settings.model_base_url` | stage 9 task 2 (`read_reply`) |
| `store.open_store`, `store.create_tables` | stage 4 tasks 1 and 9 |
| `hashing.active_ruleset_dir` | stage 12 (rule change) |
| the `*Output` aliases in `skills/contracts.py` | stages 6 to 9, one per skill |
| `hashing.plan_hash` | stage 4 task 6 (approval binding) |
| `hashing.payload_hash` | stage 4 task 7 (intents) |
| `hashing.ruleset_hash` | stage 4 task 1 (the event row's ruleset hash) |
| `digest.skill_digest` | stage 5 task 7 (skill status) |
| `anthropic` (stage 9), `pyyaml` in `src/` (stage 4 task 5, the skill manifests), the mypy override for Stand's modules (stage 3 task 1) | as named |

Known and left: `web/components.json` still names an icon library and a utils alias the scaffold no longer has (it is read only by the shadcn CLI); the `.dark` theme block in `web/src/index.css` has no switch that sets it; stage 4 makes `src/uwh/runtime/` read `skills/vertical.py`, which itself imports `runtime/event_types.py`, a package-level loop with no module cycle; §1 and `AGENTS.md` still call underwriting triage the "first vertical".

**Friction:** three review rounds in a row were blocked on the docs being out of step with the code after a shape change, not on the code. A grep of the architecture, plan and acceptance file for every name, field and file a round changed now runs before the reviewer does; it found one more stale passage (which message kinds are requests) that would have blocked a fourth round.

Process, from Brett on 2026-10-05: the lead fixes a reviewer's blocker itself and sends the fix back to the reviewer when it needs no escalation and no decision from Brett, and stops only when a blocker needs his ruling. Under that, the review at bc543ce blocked on two items and both were fixed without a further round with Brett: a blocker that is not a review accepted a cause (the refusal went with `BlockerView.review_cause`; restored on `detail.cause` with its test), and §7 and plan stage 2 task 3 said every value set lives in `event_types.py` while `AutonomyLevel` sat in `vertical.py` and the run mode in `settings.py`. The lead offered Brett two options on the second and he did not pick; the lead took the one it had recommended: `AutonomyLevel` moves to `event_types.py`, and the docs name the run mode as the one set defined elsewhere.

## Stage 02: contracts approved (stage-02-contracts-t0, 0e8ccc5)

Contracts approved by Brett at 0e8ccc5.

Brett's condition for the approval was that his rulings be made in the docs and the shapes, that the last fix rounds and those changes go to the reviewer, and that the approval be recorded at that commit if the reviewer found no blocker. The reviewer's pass over the delta to 36ca932 opened with `NO BLOCKER`; its fix-now items, which it said need no further review, are in e352606 and 0e8ccc5. From this commit the event payloads (`src/uwh/runtime/event_types.py`), the route shapes (`src/uwh/api/views.py`, `web/src/api/openapi.json`), the skill contracts (`src/uwh/skills/contracts.py`) and the domain models (`src/uwh/rules/models.py`, `src/uwh/providers/models.py`) are frozen; a change needs Brett's approval (Appendix A).

**Checks:** run by the lead at 0e8ccc5. `make check` clean: 758 fast Python tests, both drift checks, `tsc -b`, 51 web tests. `make test-slow`: 21 pass. Acceptance ids passed: S02-A1 to S02-A8. The stage 1 checks still pass; all three containers healthy.

Open with Brett, not blocking: the `blocker_opened` payload accepts what the API view refuses (a cause on a blocker that is not a review; an item kind that does not fit the blocker kind). Either stage 4's command layer gets a test that it cannot write one, which is the lead's proposal, or the check goes onto the payload, which is a change to a frozen shape.

**Next:** stage 3 task 1 (capture_world) on `stage-03-labels-t0`, branched from this branch; stage 3 stops at its gate for Brett's review of the interpretation rows. Stage 4 on `stage-04-runtime-t0`, branched from this branch.

## Stage 03: tasks 1 to 3, at the interpretation gate (stage-03-labels-t0, c730aef)

**Done:** tasks 1 to 3 of the tier-0 pass, by the rules-data author (builders on Sonnet), each reviewed by the reviewer on Opus and its findings fixed.
- Task 1: `tools/capture_world.py` records Stand's unmodified generator in process and writes `src/uwh/providers/data/world-42.json`, `world-11.json` and `world-15.json`. Seed 42's archetypes match §2.2. The two leads §9.4 names hold: `LEAD-00000011-008` has `kyc_score` not found with name and date of birth present; `LEAD-00000015-003` has `protection_class` not found with the full address present. Seed 15 also holds `protection_class` not found on 15-004 and 15-007 (the rural archetype nulled each).
- Tasks 2 and 3: `src/uwh/rules/data/derivations.yaml`, `interpretation.yaml` (rows I01 to I57, twelve choices on ten rows, seven fan-outs), `catalogue.yaml` (the eleven A.7 questions) and `wording.yaml` (61 field questions, six preambles, twelve confirmation templates). The test parses §9.7, the choices table, §9.5 and A.7 out of `docs/architecture.md` and reads the registry and Stand's class maps, so the files cannot drift from their sources. No row carries `reviewed_by`.

**Not done:** task 4, Brett's review of every interpretation row (S03-A4). Tasks 5 to 7 and 12 (cases, labels, reply fixtures, held-back replies) wait on it, and task 8 is Brett's second gate. Tasks 9 to 11 are tier 1.

**Checks:** run by the lead at c730aef. `make check` clean: 804 fast Python tests, both drift checks, `tsc -b`, 51 web tests. Acceptance ids passed: S03-A1, A2, A3. S03-A4 prints 0 of 57, as expected before the review.

### For Brett at the interpretation gate

Review `src/uwh/rules/data/interpretation.yaml`, the lenient rows first (I03, I19, I20, I21, I24, I25, I29, I30, I32, I42), and add `reviewed_by: Brett` to each row accepted. Each row's `source`, `gap`, `ruling` and `kind` are §9.7's cells verbatim. The `rationale` is not from §9.7, which has no such column: 39 were composed from the gap and the playbook page, 18 cite a sentence of the architecture, and six were rewritten after review against the pages (I22, I29, I30, I32, I46, I50).

Rulings needed, because they decide what the label author and stage 6 write:
1. **Rows no graph node can reference.** §9.6's load-time check accepts a row that a node references, that is `not_evaluated`, that carries `applied_in`, or whose page is not encoded. I02, I12 and I23 are applied only in a page's `applies_when`, which is not a node (A.6 shows `# I23` as a comment). A.6 lets only a `test` carry `interpretation`, and one row. Rows realised only in outcomes (I10, I19, I25, I34, I55) or sharing a test (I18 with I19, I24 with I25, I39 with I50) cannot all be referenced. Either `applies_when` and outcomes may cite rows and `interpretation` takes a list, or those rows get `applied_in`.
2. **7,500 square feet.** I50 puts exactly 7,500 on the stricter side in Branch A (not under 7,500, sprinklers required); I39 puts it in the middle band in Branches B and C, the lenient side. I39 is not on the lenient list; neither is I18, whose middle band is the lenient reading, nor I40 ("1,000 or less").
3. **Two choices on one fact.** `I14.access` (`adequate`, `limited`) and `I44.road_access` / `I49.road_access` (`multiple`, `limited`) ask about the same `road_access` value with different options; a lead on both Fire Simulation and PC 9 & 10 is asked twice.
4. **`applied_in` entries beyond §9.6's four categories** (validator, derivation, resolution rule, rendering step): I31 names source precedence (§9.1; added by the builder), I45 and I56 name the typed deadlines. I06 carries none: the Occupancy graph applies it.
5. **Knob-and-tube questions.** `kt_present_and_where` is filed under I51, though §9.3 rule 4 ties the combined question to the pre-1950 default and I51 is the 1950-or-later case; A.7 gives it no row. `kt_areas` offers `high_draw` or `low_draw` and has no answer for both.
6. **The KYC out-of-range confirmation template** exists because A.7 asks for one template per validator; §9.5 sends that case to the underwriter, and a system-owned score is never asked of a producer. Keep it marked for the underwriter, or drop it.
7. **`is_gated_community`** is a follow-on when its condition is unknown (§9.2 table) but has no `requiredWhen`, so no preamble exists for it. The `protection_class in (9, 10)` preamble exists and can never be used, since those dependents are `blocked`, not follow-ons.
8. **Text of §9.7 itself.** The ruling cells of I03, I06, I14 and I35 run two sentences together with no full stop; the YAML keeps them verbatim. I47's gap says "map or listing check" where the Profile page calls for a name search. I50's gap text reads as if Branch A were silent at 7,500; its box is not.
9. **`archetype_set` in the world fixtures.** Plan task 1 asks for "the archetype-set values" in each entry. Nothing reads them at run time (a lookup runs only for a missing value, and an archetype-set field is present), and they show which archetype touched a lead. Drop them and let the one stage 7 test compute them from Stand's generator, or keep them as the plan says.
10. **Wording.** `willing_to_mitigate` says "a greater distance around the home"; the board says "mitigate greater distance" and names none. Validators 9 and 10 can fire together and both name `dwelling_use_type`, so one message would ask about it twice. Six field questions say "the insured's" and the catalogue says "the client", which will not suit `direct_web` applicants (§10.3).

Left for later stages: the fingerprint must be taken over the raw `fields` as the leadgen client returns them (stage 7); six select fields list no options in their question, so reply reading maps free answers to registry options (stage 9); `derivations.yaml`'s `divisor` repeats its second input and `statement` is read by nothing; `lenient` and `question_for_stand` have no reader after this gate.

**Friction:** one builder returned the word "placeholder" as its whole report after committing; the lead verified its commit by reading the tests and running the checks, and could not confirm the builder had shown each rewritten test failing first. Builder prompts now say the final message must be the full report.

**Next:** Brett's review of the rows (task 4), then tasks 5 to 7 and 12 by a fresh label author on the lead's own model. Stage 4 starts in a worktree under `.worktrees/` from the approved stage 2 commit, so that Brett's edits on this branch and the stage 4 builders never share a checkout.

## Stage 03: Brett's gate rulings applied; the row review is still open (stage-03-labels-t0, 627f944)

**Done:** Brett ruled on the ten points of the gate entry above and edited `docs/architecture.md` himself (committed at 537fb93 with the plan reconciled to it). Builders on Sonnet applied the rulings, and the reviewer on Opus read the result and found no blocker.
- §9.7 text: the YAML follows the amended cells of I03, I06, I14, I35, I39, I44, I47, I49 and I50. I39 states the boundary rule: exactly 4,000 square feet is in the middle band, and exactly 7,500 is treated as larger than 7,500 in Branches B and C, as in Branch A.
- One road-access choice, `I14.road_access` (`multiple`, `limited`), carried by I14, I44 and I49: ten choices on ten rows.
- `applied_in` takes the form `<category>: <what> (<citation>)`, the category one of the six §9.6 names, a graph page named by its playbook folder. 23 rows carry it: validator I01, I53; derivation I20; resolution rule I31, I51, I57; rendering step I47; effect field I45, I56; graph page I02, I05, I06, I10, I12, I19, I22, I23, I25, I29, I34, I43, I48, I55. The test ties a graph page to the row's source page and a validator to its §9.5 row.
- Catalogue and wording: `kt_areas` says any high-draw area is answered high draw; `willing_to_mitigate` uses the board's words; "the applicant" replaces "the insured" and "the client"; the KYC range template and the `protection_class in (9, 10)` preamble are gone (five preambles, eleven templates).
- `derivations.yaml` holds `operation` and `inputs` only. The world fixtures hold `fingerprint`, `provider_values` and `fields`; `archetype_set` and the recorder's `set_values` are gone.
- The lead reconciled §9.2, §9.5, plan stage 6 task 3 and plan stage 7 task 2 with Brett's A.7 text (0c6754f), for Brett to check.
- `design-polish-message` (e4a3d68, docs only: the tier-1 rewrite of request emails as stage 8 task 11) is merged; its worktree and branch are removed.
- `tests/tools/test_check_generated_types.py` runs the tool with its own `TMPDIR`: two `make check` runs in two checkouts had each seen the other's temporary directory.

**Not done:** task 4, Brett's review of every row (no row carries `reviewed_by`; `lenient` and `question_for_stand` stay until that review is recorded). Tasks 5 to 7 and 12 wait on it.

**Checks:** run by the lead. `make check` clean at 627f944: 808 fast Python tests, both drift checks, `tsc -b`, 51 web tests. `capture_world --check` passes for seeds 42, 11 and 15 (builder and reviewer). S03-A2 needs the containers and was not rerun after the fixture change.

**Open with Brett:**
1. Validators 9 and 10 firing together must ask `dwelling_use_type` once (ruling 10). A.7 gives one template per validator and nothing defines a merge. Options: a combined template in `wording.yaml` for the pair (the lead's recommendation: fixed wording a test can pin), or a merge rule in §10.2 with the text composed in code. It decides stage 8, not the row review.
2. No §9.7 row carries the pre-1950 knob-and-tube default (§9.3 rule 4 alone does), so `kt_present_and_where` stays under I51.
3. "Boundary values take the stricter band on every page": the amended §9.7 states it in I39 only. Read across every page, I18 (exactly 0.50), I24 (exactly 30 and 10 years) and I30 (exactly 120 amps) take the lenient side. Left as they are.
4. I05, I22, I29, I43 and I48 gained a graph-page `applied_in` on the reviewer's reading that no `test` node can cite them; the builder checked only I05 against its page. I32 is taken as the row the `pool_security` test cites. Unsure and left without: I03, I42, I52.
5. No plan task tests "a lead on both pages is asked once" for road access; a tier-1 case in stage 6 should.

**Friction:** the Stop hook ran `make check` in one checkout while a builder was mid-task in it, twice; both reds were the builder's failing-test-first step. Two checkouts running `make check` at once exposed the shared-temp-directory test.

**Next:** Brett's row review (task 4) and the open points above, then tasks 5 to 7 and 12 by a fresh label author on the lead's own model.

## Stage 03: Brett's second set of answers applied; the row review is still open (stage-03-labels-t0, 9854f2a)

**Done:** Brett answered the open points of the entry above; the architecture carries them at 94d374c and the data at cc989ce and 9854f2a.
- §9.7 states the boundary test once: where the board states both sides of a line and leaves the exact value in neither, the exact value takes the stricter band; where it states one side only, the literal reading holds. I18 (Roof, bands "> .15 < .50" and "> .50"): exactly 0.50 takes the high band. I24 (Plumbing, "older than" and "newer than"): exactly 30 years and exactly 10 years are older. I30 (Electrical, "less than 120 amp" only): the ruling stands as a literal reading. I24 and I30 are off the lenient list. I39 and I50 agree with the test as they stood.
- `wording.yaml` holds a `combined_confirmation` that replaces the two `dwelling_use_type` validators' confirmations when both fire (A.7); no merge rule in §10.2.
- `kt_present_and_where` is filed under I27. No row is added for the pre-1950 default.
- The reviewer checked I22, I29, I43 and I48 against their playbook pages: all four match and each needs its `applied_in`; I32 is the row the `pool_security` test cites. The `applied_in` notes of I22, I29 and I43 no longer credit the board with what it does not draw. I03, I42 and I52 can each be cited by one test and carry none.
- S03-A2 rerun against the leadgen container after the fixture change: 3 passed.

**Not done:** task 4, Brett's row review. Tasks 5 to 7 and 12 wait on it.

**Checks:** run by the lead. `make check` clean at cc989ce: 809 fast Python tests, both drift checks, `tsc -b`, 51 web tests; the builder reported exit 0 at 9854f2a.

**Open with Brett, for the row review:**
1. I48 reads leniently and is not on the lenient list: an unfenced inground pool in a gated community gets a recommended cover where "Fenced = No" would require one. Add it to the list, or state in its rationale that "Fenced = No" is for fenced pools without a gate or cover (I32); its "unreachable" claim holds only given I32.
2. I43's ruling skips the fittings question for a home with no dry hydrant and does not say so.
3. I22's rationale does not mention the registry's siding class A as the other reading of "Class A"; I42's ruling does not say None and Local Alarm get the requirement.
4. Other validator pairs list a shared field. Read from the templates, only the pair the combined template covers can ask about one field twice in a message, except the two roof-year validators when the roof year is in the future and before `year_built`. Not tested; no template added.
5. For stage 6: citing I52 through `roof_age_years` adds a `p_f` dependency to Class A roofs, so a blocked `p_f` could hold a packet for an advisory. Whether a seed-42 lead hits it is unchecked.

**Next:** Brett's row review, then tasks 5 to 7 and 12 by a fresh label author on the lead's own model.
## Stage 04: tasks 1 to 5 and 8, held for Brett's rulings (stage-04-runtime-t0, f5ad355)

Stage 4 runs in the worktree `.worktrees/stage-04-runtime-t0`, branched from the approved contracts commit 1f25204, so that Brett's review of the interpretation rows on `stage-03-labels-t0` in the main checkout and the stage 4 builders never share a tree.

**Done:** builders on Sonnet, each task reviewed by the reviewer on Opus and its findings fixed.
- Task 1, event log (`src/uwh/runtime/events.py`): one typed event appended with its run id, mode, actor, ruleset hash and both timestamps, none of them optional; `lead_id` a required argument that may be None; the caller commits. Events read back in id order.
- Task 2, clock (`clock.py`): simulated time, business-day age in UTC, `add_business_days`.
- Task 3, fact ledger (`facts.py`): the ten §7.3 rules as named tests; `fact_selected` events alone rebuild the effective facts (§12); the lead revision moves exactly when an effective fact changes, plus rule 9.
- Task 4, blockers and workflow (`waits.py`, `workflow.py`): opening a blocker refuses anything the lead detail view would refuse to serve; transitions only along A.3; steps in order, one transaction per step; a failing step rolls back and opens one `data` blocker at top level, and propagates inside a caller's transaction so nothing commits; re-evaluation re-runs the whole sequence; a pool of four leads, one connection per lead.
- Task 5, skill registry contract (`skills/__init__.py`, `manifest.py`): `SKILLS` is empty until a stage adds a skill; the manifest carries the §8 fields and loads without `cases/`, which the image strips.
- Task 8, recordings and record mode (`recordings.py`, `modes.py`, the `./recordings` mount): live never reads or writes a recording, record calls and writes, replay reads and raises on a miss; a failed live call is never answered from a recording.

**Not done:** tasks 6 (command layer), 7 (send primitive), 9 (run start) and 10 (integration faults), and the tier-1 tasks 11 and 12. Tasks 6, 7 and 9 are held: each depends on a ruling below. No acceptance check of stage 4 has been run; none is marked.

**Checks:** run by the lead at f5ad355 in the worktree. `make check` clean: 1,035 fast Python tests, both drift checks, `tsc -b`, 51 web tests. The slow workflow test passes. The frozen contracts are unchanged since 1f25204.

Decisions the lead made, for Brett to confirm or change:
- **Statuses.** A new lead is `received`; it becomes `triaged` when its first step completes and `in_progress` when a whole pass has completed; `in_progress` re-enters itself on re-evaluation; the terminal statuses are set only by an explicit transition when a packet or notice is sent. The architecture names the statuses and not what sets each.
- **One transaction per step.** Each step runs in one `BEGIN IMMEDIATE` transaction, a savepoint inside a caller's transaction. SQLite has one write lock, so step bodies of different leads never overlap; the pool keeps up to four leads in flight, a lead counting from the start of its pass to its end. The slow test asserts that count never exceeds four; with the bound raised to ten it failed twenty runs of twenty, and at four it passed twenty of twenty. Splitting a step into a call phase and a write phase, or changing the journal mode with retries, would let step bodies overlap; nothing needs that, since no workflow step makes a slow external call and the mailbox post runs outside any transaction (§7.5).
- **Opening a blocker refuses what the view refuses**, in `waits.py`, with a test tying the two; no frozen shape changed. This is the lead's answer to the open question recorded at the contracts approval.

### Rulings needed before tasks 6, 7 and 9

1. **Events before the first run.** The event log refuses an event with no run id, and S04-A5 requires none null, but `emergency_stop`, `change_setting` or a refused command can arrive before any run exists, when there is no run start to compute simulated time from. Options: refuse every command but `start_run` until a run exists; stamp a fixed pre-run id with the reference morning as simulated time (the lead's proposal: settings persist across runs, so they must be changeable before the first); or allow nulls, against S04-A5.
2. **A command whose re-evaluation produces an automatic send.** A.11: every accepted command re-evaluates its lead in the same transaction. §7.5: dispatch commits `dispatching` in its own transaction and posts outside any. Proposed: re-evaluation inside a command builds drafts only, and automatic drafts are dispatched after the command commits.
3. **A failing step during a command's re-evaluation.** Built as plan task 6 says: nothing commits and the command fails. The cost: a defect in one skill makes every command on that lead fail, `resolve_fact` included. The alternative commits the command with a `data` blocker (§8).
4. **Can the underwriter settle a conflict?** `resolve_fact` on a key in an open conflict leaves the conflict open and the fact unusable; only a producer's reply closes it. Rule 1 says an underwriter ruling outranks everything. Proposed: `resolve_fact` closes the conflicts on its key, and the validator does not reopen them on the same values.
5. **Late replies (rule 9, A.3, A.11).** Built: recorded `pending_review`, applied to nothing, reviewed with cause `late_reply` or `reply_after_terminal_status`; the values reach the facts only through `resolve_fact`. The recorded values then stay pending with nothing able to settle them, and the review names neither the intent nor the observations. Proposed: keep the reading, have the review name its intent, and mark the values rejected when the underwriter acknowledges it.
6. **A reply that differs from a value the underwriter ruled** is recorded `rejected` and raises no review. Confirm, or raise a review.
7. **`resolve_fact` and pending observations.** Approving a pending observation after a `resolve_fact` on the same key replaces the underwriter's later value with the older reply value. Proposed: `resolve_fact` settles (rejects) the open pending observations on its key.
8. **A reply value that both differs from a submitted value and trips a validator** follows rule 3: pending, no conflict opened. Confirm.
9. **What closes a step-failure `data` blocker.** Nothing does, and repeated failures open duplicates. A.11 has no item for a `data` blocker, and the frozen `BlockerDetail` has no field naming the step.
10. **A lead stopped early cannot be declined.** A.3 has no path from `received` or `triaged` to `declined`, so `decline_lead` cannot end a lead that a `data` blocker stopped before its first pass completed.
11. **A lead interrupted by a crash mid-pass** stays `received` or `triaged` with no blocker and nothing re-runs it. Should startup open a `data` blocker on it?
12. **No event records a status change** (A.2 has none), so the status history, a live update for a bare transition, and "when did this change" are not in the log. Accept, or it is a change to the frozen contracts.
13. **`add_business_days` has no user.** Plan task 2 requires it with a property test; nothing in the architecture adds business days to a date, and its weekend rule disagrees with the age (a Saturday 23:00 lead plus one business day is Monday 23:00, while its age then is 0.96). Proposed: drop it from the plan and the code.
14. **The blocker rules exist twice,** in `waits.py` and in `BlockerView`, tied by a shared test table. One function both call needs an import and a call in the frozen `src/uwh/api/views.py`, with no shape change.

Notes for the held tasks, from the reviews: the command layer runs each command under one `BEGIN IMMEDIATE` with the re-evaluation inside; it needs `load_manifest` and the issuing skill's name to refuse a class a manifest does not declare; `approve` and `reject` of an observation write no event of their own, so `approval_recorded` goes in the same transaction. The send primitive refuses to run inside a transaction, checks the terminal transition before the post and applies it in the transaction that records `sent`, and builds a fresh context after the post so `message_sent` is not dated before it. Run start commits the lead rows before the pool starts, settles in a `finally`, and `first_pass_complete` reads `runs.status`, never `run_is_settled` while a pass may be running. "A pending approval returns to review" (task 3's rule 9 sentence) and "stale drafts and approvals return to review" are asserted in the ledger only as the revision moving; tasks 6 and 7 must assert the rest.

Unread items now read: `vertical.TRANSITIONS`, `TERMINAL_STATUSES` and `BLOCKER_KINDS_BY_PRIORITY` by `workflow.py` and `waits.py`; `pyyaml` under `src/` by `manifest.py`. Still unread: `vertical.COMMAND_CLASSES` in the runtime (task 6; `manifest.py` reads it for the classes a skill may issue), `REFERENCE_MORNING` (the clock takes it as an argument; task 9's run object passes it), `Settings.db_path` (task 9), `hashing.plan_hash`, `payload_hash` and `ruleset_hash` (tasks 6, 7 and 9).

**Friction:**
- The lead gave a builder two instructions that cannot both hold: one transaction per step, and a test that four leads run inside a step at once. The builder reported the contradiction and left the test failing instead of weakening it or choosing a design. The lead decided, and the test now measures leads in flight at pass level.
- The lead endorsed a builder's "each step manages its own transactions" design to Brett before the review; the reviewer showed it could split a step's writes and leave a half-written lead that looked settled. Design claims go to the reviewer before they go to Brett.
- A builder's brief named S04-A2 for the "no column null" check; it is S04-A5.

**Next:** Brett's rulings above. Then task 6 (command layer), task 7 (send primitive), task 9 (run start), task 10 (integration faults), verify, cross-review and the stage entry.

## Replan: one branch, seven milestones (submission, 3db8b9a)

Brett replaced the staged plan with `docs/plan.md` from branch `replan` (1625f9a): the build had reached about 14,600 lines of tests with no lead processed end to end. Stages 3 and 4 are merged into the one branch `submission`; every other worktree and branch is removed. The entries above this one describe the staged plan and its open rulings; rulings that concern cut items need no answer.

Brett's decisions carried into milestone 1: an underwriter's value that still trips a validator opens no conflict and sends no confirmation; a draft built at an older lead revision is never sent and re-evaluation replaces it; a lead with an open `delivery_unknown` item sends nothing automatically; item ids never repeat across runs if that is a small change, with no run id on commands. The lead's own: `read_reply` calls the model outside the database transaction, then one short transaction records and re-evaluates; a failed first pass leaves each unfinished lead with a `data` blocker and its reason; `start_run` is refused while an intent is `dispatching`; a waited start reports the run it started. Brett reviewed the interpretation rows; he signs the ten seed-42 labels in milestone 2; I52's `p_f` dependency goes to him only if a seed-42 lead is held by it.

## Milestone 0: Reset (8aced52)

**Done:**
- Rules: `AGENTS.md`, the `stage`, `verify` and `cross-review` skills and the builder and reviewer definitions follow the new plan. `scripts/check_discipline.py` no longer requires a test file per module.
- Tests: 1,555 collected before, 322 after. Python lines under `tests/`: 14,614 before, 5,552 after. Twelve test files of the excluded kinds are gone; the kept files hold about one test per fact rule, send-safety property, command effect, stale-run and startup property. The eight named safety tests pass.
- Code: Python lines under `src/`: 5,712 before, 5,380 after. Removed: the `settings` table, emergency stop, `change_setting`, the rule-change flow, demotion, held drafts, the `off` level and locked classes, the MCP actor, the settings, skills and event-stream routes, `run_is_settled`, `tools/standin_api.py`, the seed 11 and 15 world fixtures, `MailboxClient.get`, `RevisionChange`, `binding_changes`. `CommandEnvironment` is `RunEnvironment` in `runs.py`.
- Data: 23 interpretation rows of the five cut pages deleted; 34 remain, each `reviewed_by: Brett`, I18 at the stricter band; `lenient` and `question_for_stand` removed. The catalogue holds `willing_to_mitigate` and `rce_documentation`.
- Architecture: 1,054 lines before, 987 after; §4.1 states the cut line; tiers, cut pages, MCP, SSE, settings, the stop, rule changes, the sweep, extra controls and packet cases are out; the appendix agrees with the tables, events, routes and commands in code.
- `docs/acceptance.json` holds the three milestone 1 checks.

**Not done / carried:** nothing under `src/` reads yet: the skill contracts, the view models and stubbed routes, `Settings.model_id`, `model_base_url`, `registry_path`, `git_commit`, `CONFIRMATION_ONLY_CLASS`, the `identity_score_*` review causes, several event types (`triage_completed`, `plan_built`, `provider_called`, `reply_received`, `reply_read`, `model_called`, `skill_fallback_used`, `proposal_created`, `replay_miss`). Each is read by a milestone the plan names; whatever is unread when that milestone ends is deleted then. The architecture keeps old "stage N" references in a few sections and skill-status text in §8; the milestone 6 removal pass takes them. The lead-detail display fixtures under `tests/fixtures/ui/lead/` list twelve pages; they go when the queue page reads live data.

**Checks:** `make check` clean, run by the lead after the second prune: 303 fast Python tests, both drift checks, `tsc`, 51 web tests. The builder reported it clean after the architecture commit.

**Decisions:** tests deleted with no replacement under "delete borderline": startup reconcile with the mailbox down, `approve` of `delivery_unknown` with no message, one stale-run command test. A cut page that applies to a lead (Plumbing and Electrical apply to every lead) shows as a `not_evaluated` note naming the page.

**Next:** milestone 1: lead 008 from the queue to a sent quote packet.

## Milestone 1: One lead, end to end (4983aeb)

**Done:** `LEAD-00000042-008` runs from the posted queue to `quote_sent` through the running app, and the three acceptance checks pass on the containers: M1-A1 (the integration test drives it against real leadgen and mailbox), M1-A2 (the mailbox holds one request and one packet), M1-A3 (the queue and the detail are served from live data; the lead was also approved from the browser).
- Rules core: registry loader, field triage (§9.2), the eleven validators, derivations, the Roof, Siding and Replacement Cost graphs with a band-completeness load check, `_not_encoded.yaml` with a producer sentence per cut page.
- Skills as workflow steps: `triage_fields`, `resolve_data` (stand-in providers from `world-42.json`, `fetch_data` checked against the manifest), `evaluate_playbook`, `ask_producer` (`plan_asks` → `render_message` → `create_draft`), `build_quote_packet`; `read_reply` on DeepSeek through a forced tool call, record and replay keyed by the prompt and tool schema and the input the model is shown. Order in `skills/vertical.py`.
- Commands and routes: `deliver_reply` (the model call outside the transaction, one short transaction after), `POST /api/replies`, `POST /api/replies/fixtures`, `GET /api/leads`, `GET /api/leads/{id}`; the queue page and detail pane on live data with Start, Deliver fixture replies and Approve.
- Brett's decisions: a ruled value that still trips a validator opens no conflict; a draft built at an older revision is never sent and re-evaluation replaces it; an open `delivery_unknown` stops every automatic send; item ids never repeat across runs; `start_run` refused while an intent is `dispatching`; a waited start reports its own run; a provider or model error leaves the reply unread with an underwriter review.
- The other leads: 001, 004 and 009 send one routine request each; 000, 002, 003, 005, 006 and 007 stop with a `data` blocker naming the page milestone 2 builds.

**Live calls:** one record run of `read_reply` on lead 008's fixture reply: 1,165 input, 148 output tokens (`deepseek-flash`). One unplanned live call from the app container in `live` mode when the fixture reply was delivered on the running app: 141 input, 148 output tokens. Project total: 1,306 in, 296 out.

**Checks:** `make check` clean at 4983aeb, run by the lead: 419 fast Python tests, 3 web tests, both drift checks. Python lines: `src/` 7,318, `tests/` 7,322. The reviewer read the milestone once: no blocker; its findings are fixed (a resend after an ambiguous delivery waits for approval; the recording key covers the tool schema; a model error is the unavailable case; producer wording; the fixture control in the queue header).

**Decisions:** a missing or mismatched provider entry gives `unavailable` and a `data` blocker, not a stub value (§9.4 amended). Graph files carry no `branch` key; one load-time check covers numeric bands (A.6 amended). RC-4: a coverage ratio above 1.5 is a documentation requirement in the packet, since the architecture states no `documentation` outcome. Triage runs before and after resolution, because a fetched value changes its dependents' triage. `producer_text` per cut page lives in `_not_encoded.yaml`. DeepSeek returns no request id; `model_called` stores none. Replies to confirmations and catalogue questions are not read yet (milestone 2).

**Open with Brett:** the default `RUN_MODE` for `make up` (proposed: `replay`, so a demo never spends money); RC-4's wording; whether cut-page registry fields (`electrical_panel_brand`) should be asked.

**Next:** milestone 2: the other nine leads, the Profile, Occupancy, Fire Simulation and Post & Pier graphs, the decline path, underwriter choices; Brett signs the ten labels.

## Milestone 2: All ten leads (f8f5b91)

**Done:** a run leaves every seed-42 lead at a sent request, a proposed decline waiting for approval, or an underwriter card, as the §5 table says; no lead has two open requests; Stand's answer key agrees on every record it decides. M2-A1, M2-A2 and M2-A3 pass on the running containers, run by the lead.
- Graphs for Profile, Occupancy, Fire Simulation and Post & Pier from the boards and the reviewed rows, with the three-valued interpreter, `producer_question`, `underwriter_choice`, `all_of` and `ladder` nodes, and load checks: numeric bands complete, no dangling or unreachable node, every interpretation row cited by a node or `applied_in`.
- Underwriter choices as one card per lead (`record_ruling` validates the option, closes the card when every choice is answered, re-evaluation takes the branch); the proposed decline with its notice (`approve` sends it and the lead is `declined`; `reject` reopens the directly deciding choice or suppresses the declining rules, and the registry asks go out); `decline_lead`; the two-round limit with the persisting `round_limit` review, closed when the lead becomes a proposed decline; confirmation and catalogue answers in `read_reply`; the I52 roof-age advisory.
- A conflict covers only the fields that are present, so a missing field in a validator's trigger is still asked (lead 004's `dwelling_use_type`; the one record on which the key had disagreed).
- `evals/graders/answer_key.py` regenerates seed 42's debug history in process and grades every record by §13.2; the test pins the counts: 190 agree, 26 exempt on lead 000's proposed decline, 0 exempt as blocked, 5 inactive conditionals, 1 set again by a conflict, 0 disagree.
- The ten labels under `evals/labels/seed42/` and `excluded_edges.yaml`, written by a fresh author on the lead's model from the playbook, the registry and the data files, without the rules code; the ask sets match the run for all ten leads. Brett signs them; the label/code disagreements are in the hand-back (000's status and Roof outcome, the ladder advisories, decline text, two effect wordings).

**Live calls:** none. Reply tests other than lead 008's use hand-made readings in a temporary directory to test the code after the model; AGENTS.md prefers recordings.

**Checks:** `make check` clean at f8f5b91, run by the lead: 538 fast Python tests, 3 web tests, both drift checks; integration 15 passed. Python lines: `src/` 7,964, `tests/` 9,189. The reviewer read the milestone once: no blocker; its findings are fixed (two Fire Simulation traces, ladder rungs, declines under an answered choice, the round-limit review after a decline, the grader's pinned counts and post-resolution triage, plain-words texts, applicant wording).

**Decisions:** rulings are read from `ruling_recorded` events, not stored as facts, and move the lead revision. The Profile ladder's later rungs are internal advisories, shown to the underwriter and never sent in a packet. A packet carries no note that a decline was overridden. A sent packet or notice closes the open request. `RuleTrace.choice_ids` names the choice that directly decides the outcome. A `direct_web` lead's request says "your" in place of "the applicant's". `triage_completed` is written before and after resolution; the later one is current. The decline notice states no reason. Not built because no seed-42 lead reaches them: the KYC range validator (I01) and its `identity_score_*` reviews, the `no_contact_route` item; each path stops with a stated `data` blocker. The architecture is amended for the obligation line (no owner), the ladder row and what a rejection reopens or suppresses.

**Open with Brett:** the label signatures and the disagreements above; the wording of RF-5 ("A review of the roof's condition before binding, because a composition shingle roof more than 20 years old is a higher risk.") and the mitigation question ("Would the applicant be willing to mitigate greater distance?"); the default `RUN_MODE`.

**Next:** milestone 3: `make eval` with the seed-42 suite and graders, the reply suite, the three controls, per-skill cases, the results log, one improvement cycle on reply reading.

## Milestone 3: Evals (12917bf)

**Done:** `make eval` runs in the containers against its own leadgen and mailbox services, from an empty database, in replay. M3-A1 (the reference run passes every grader), M3-A2 (do nothing is caught by Coverage, email everything by Forbidden asks and Asks, send twice by Send safety and One open request) and M3-A3 (the log shows the improvement cycle and Brett's keep decision) pass, run by the lead.
- Runner `evals/run.py` (`--suite seed42 | replies`, `--control`, `--hypothesis`), refusing a dirty tree so a row's commit names the code that ran; the graders Coverage (statuses, underwriter items, not-evaluated notes), One open request, Asks, Forbidden asks, Rule trace, Packet fidelity, Reply facts, Send safety (two fault runs on lead 008), Stand's key (counts pinned in `evals/labels/seed42/exemptions.yaml`), Reply reading; the four critical errors; the three controls as runner seams; `cases/` for `evaluate_playbook` (82 rows) and `read_reply` (8 fixtures); skill digests, evaluator hash and `skill_results` on each row; `src/uwh/skills/status.py` reads a skill's status from the log (milestones 4 and 6 read it).
- Eight reply fixtures with expected readings (`fixtures/replies/`, three held back under `held/`; `evals/labels/replies/`), written by a fresh author on the lead's model.
- The improvement cycle in `evals/results.jsonl`: a run failing on held-back lead 005 (`state` read as "Colorado"), one prompt clause (return the shortest conventional form), the rerun passing that value, then a code rule deciding `answers_all` from the asks because the model cannot see which follow-ons its own answers made inactive, the final run 8 of 8, and Brett's `decision` row keeping it. Two rows run on an uncommitted tree carry `decision` rows discarding them.
- Brett's rulings: lead 000's label status is `in_progress`; a restated confirmation closes its conflict and a filled missing field of the pair does not reopen it (lead 004 goes to a quote packet); the label word `pending_observation` became the contract's `observation`.

**Live calls:** two record runs of `read_reply`, nineteen calls, no retries: eight fixtures 8,036 in / 2,869 out, then nine fixtures after the prompt change 8,923 in / 2,994 out. Project total: 18,265 in, 6,159 out. Lead 008's re-recorded call reports 391 input tokens against 1,165 the first time, for the same input; unexplained.

**Checks:** `make check` clean at 44723b7, run by the builders: 625 fast Python tests; the lead ran the acceptance commands and the integration tests (pass). Python lines: `src/` and `tests/` to be recounted in milestone 6.

**Decisions:** the classification of an on-topic reply is decided by code from the asks (§10.4 amended). Replay rows count toward a model skill's status (§8 amended); the three-repeat check is not run (§13.3). The per-page case-coverage check and `excluded_edges.yaml` are dropped; cases are a table per page (§13.2). The graders Field resolution, Escalation, Approval binding, Policy and Key isolation are cut (Brett); `threshold_reason` is removed. `alternatives` and `held_catalogue_questions` in the 003/006 labels are unread. The reviewer's milestone 3 read found six blockers, all fixed above; findings on unreached paths: none.

**Open with Brett:** the label signatures (`reviewed_by` on the ten seed-42 files); the default `RUN_MODE`.

**Next:** milestone 4: the underwriter surface.

## Milestone 4: Underwriter surface (8c470db)

**Done:** every action an underwriter needs on the ten leads works from the browser against the running app, and the chat cases pass in the eval. M4-A1 (nine action tests through the app's routes against the containers), M4-A2 (the web tests) and M4-A3 (the chat suite row) pass, run by the lead.
- Routes: `GET /api/items`, `GET /api/leads/{id}/events` (a sentence per event, `src/uwh/api/event_summary.py`), `POST /api/chat`, `GET /api/proposals`, `POST /api/proposals/{id}/apply|dismiss`. The 501 stub module is gone: every A.5 route is served.
- Pane: Approve with a reason, Edit and Reject on drafts ("Withdraw decline and send the asks" on a decline notice); Approve and Reject on a pending value, shown beside the value it would replace; Acknowledge on an event-raised review; one question card per lead with equal option buttons, no default and a required reason; Resolve fact from a select of the lead's fields, sent in the registry's kind, refusing an unknown key; Decline lead; Paste a reply against the latest sent request; Open items across leads; the event list; refetch after an action and on an interval.
- Chat (`src/uwh/chat/`): one forced `chat_step` tool per call with the actions `lead_events`, `lead_summary`, `open_items`, `answer` (cited event ids) and `propose_command`; at most four steps per turn; a proposal is stored as a card the underwriter applies or dismisses; a directive to approve, reject or send is refused by the actor rule and the answer points to the lead's open item; the Chat grader and `--suite chat`; three cases with eight recordings; the chat prompt's digest on the row.
- Two builders ran in parallel worktrees; the lead merged both and resolved three conflicts.

**Live calls:** one record run for the chat cases: eight calls, 9,241 in / 737 out. Project total: 27,506 in, 6,896 out.

**Checks:** `make check` clean at 8c470db, run by the builder (733 fast Python tests, 27 web tests); the lead ran the acceptance commands and the integration tests (pass). `make check` takes about 80 seconds; the in-process API tests each run a full seed-42 pass.

**Decisions:** the chat's single tool with an `action` field reuses `read_reply`'s forced-call and recording mechanism; the apply and dismiss routes are additions to A.5; the chat eval holds the run at its start so event ids are stable across runs; `src/uwh/chat/cases/` is exempt from the discipline word list as quoted voice ("most recently"), a reword would cost two live calls; the chat `lead_events` tool still returns the raw event payloads to the model, because the tool result is in the recording key and changing it needs a re-record (milestone 6, with any chat re-record). The reviewer read the milestone once: no blocker; its findings on what the underwriter sees are fixed; removals left for milestone 6: `ProposalView.state`/`actor`/`event_id` unread by the web, the dismiss route's body.

**Open with Brett:** the label signatures; the default `RUN_MODE`; any item on his presentation list beyond the pass above.

**Next:** milestone 5: the Jev adapter (ask Brett before the first live Jev call), then `polish_message`.

## Milestone 5: Jev and the email rewrite (c9a8b3d)

**Done:** M5-A1 (the reply suite passes with Jev answering first and with no Jev key), M5-A2 (a routine request in the mailbox carries the rendered question block unchanged inside a rewritten opening and closing) and M5-A3 (a rewrite that fails a check sends the rendered request) pass, run by the lead.
- The Jev adapter (`runtime/jev_client.py`, `read_reply/jev.py`): one choice question per reply over the body with the four classifications as options, record and replay under `recordings/jev/`, no retries; confidence over three outcomes (on-topic as `answers_all` + `answers_some`, since code decides all versus some; `off_topic`; `declines_to_answer`), threshold 0.7; a Jev error or a missing recording falls back to the model and is logged; each Jev call is a `model_called` event under its model id. Jev classifies seven of the eight reply fixtures at 1.0; the off-topic reply (006, Jev 0.64) goes to the model.
- `polish_message`: two calls per request (the rewrite, then the judge), the body as opening + the rendered question block byte for byte + closing, the rendered request on any failure with the rejecting check logged. The prompt claims nothing about what anyone has done and the judge fails a claim about what was done or a promise about what will be asked. Two of nine round-1 rewrites are rejected by the judge.

**Live calls:** polish record run 18 calls, 8,479 in / 1,489 out; the demo record run 24 polish + 9 `read_reply` calls, 9,846 in / 4,141 out on DeepSeek, and 9 Jev questions, 4,771 in / 468 out. The stored `tokens_in` is the provider's `input_tokens` alone and leaves out cached input, so every input total in this log undercounts.

**Checks:** `make check` clean, run by the lead; integration 27 passed; the reviewer read the milestone once: no blocker on the rewrite path; the Jev replay miss became a fallback.

**Decisions:** a missing Jev recording falls back to the model (§7.7, §10.4); the polish calls run before the step's unit of work; `polish_message` has no case table (the plan names two skills with cases); a rejected rewrite is recorded as `rejected`; the Jev interface was built from TypeSafe's published docs and verified by the first live calls.

## Milestone 6: Submission (4b6e0ab)

**Done:** M6-A1 (a keyless fresh clone runs: `tools/fresh_clone.py`), M6-A2 (replay reproduces the demo with no `replay_miss`) and M6-A3 (the README with the five sections; the reviewer and the cross-review report no blocker on a seed-42 path, no double post, no unapproved send, no live call from replay) pass, run by the lead. Replay is the default mode; `live` and `record` are set on purpose. The removal pass: skill status (nothing read it), unread proposal-card fields, six duplicate or shape-only test files; one seed-42 pass shared across the API and eval tests, `make check` from about 103 to 34 seconds; the chat's `lead_events` tool returns the page's summaries (chat re-recorded: 8 calls, 4,229 in / 753 out). Tests collected 825 → 770; Python lines `src/` 9,189 → 9,139, `tests/` 12,431 → 11,923: the test tree stays larger than `src/`, and what remains is the send-safety, fact-rule, playbook-outcome, command-effect, reply-reading and grader tests.

**Known limits, from the two reviews and left as they are (a proof of concept, by Brett's direction):** a chat turn that finishes after a new run started writes its proposal into the new run; proposal-card ids restart with a run (blocker ids do not); an edited draft is not checked for pricing, decline reasons or internal notes before sending (§10.2 names the check; the underwriter approves every edited draft); the Asks graders read the stored ask ids, not the delivered body; a round-2 rewrite runs inside the command's transaction; the runtime does not gate a skill on its eval status; `Reply facts` is scored beside the nine graders; dismissing a proposal card writes outside the command layer; the chat panel cannot answer in the replay demo (its recordings predate the first pass); a post in flight when a run is replaced can reach the mailbox; the paths no seed-42 lead reaches stop with a stated `data` blocker.

**Open with Brett:** the ten label signatures (`reviewed_by` in `evals/labels/seed42/*.yaml`).

**Next:** Brett's review of the submission.

## Chat surface 1: Server (219da4b)

**Done:** the server half of `docs/chat-surface.md`. C1-A1 (the pinned server tests: 82 pass), C1-A2 (the chat suite from its recordings, `make check` clean) and C1-A3 (lead 008's events read as sentences through the running app's events endpoint) pass, run by the lead.
- `event_summary` writes narrative sentences ("Triaged the fields: 14 missing", "Fetched the replacement cost: 928992", "Jev classified this reply (0.83, at or above the 0.70 threshold). ..."); nothing cuts them.
- `EventRow` carries `item_id`, `fact_key` and `message`; `FactView` carries `event_id`; `ProposalView` carries `lead_id`.
- Six lookups in `src/uwh/chat/tools.py` (lead events, lead summary, messages, playbook path, current draft, queue summary) with turn-local reference numbers; an answer's citations are resolved by the server and a number no lookup showed is dropped. `plan_pages` groups a stored plan by page.
- `ChatRequest.history` (at most four exchanges), the prompt for the lookups, the numbers and the history; the proposable set is the four commands.
- `POST /api/chat` answers as a server-sent-events stream: `step` per lookup, then one of `answer`, `proposal`, `error`. The turn runs in its own thread. Replay closes with "Questions need live mode" and calls no model.
- The chat eval sends a case's earlier turns as history and runs the lead 001 case after the first pass and the fixture replies; the grader reads resolved citations. `ChatPanel.tsx` reads the stream.

**Live calls:** two record runs of the chat suite on `deepseek-flash`: 11 calls, 11,678 in / 993 out, in which the reworded refusal used its four steps on lookups and wrote no refusal; then, after one prompt sentence (an instruction is proposed at once), 9 calls, 10,892 in / 942 out, all five turns passing. The specification names one re-record; the second is the fix for the failing case. Jev: none.

**Checks:** `make check` clean at 219da4b (763 fast Python tests, 29 web tests); `make test-slow` 33 passed and the chat suite's replay row passes, both at 1428848. The reviewer read the milestone once: one blocker (a turn whose thread raised left the stream open and the panel on "Working…"), fixed with a test; its removals (an assertion that could not fail, `TurnResult.exchanges`, stale wording in the manifest and the `propose_command` refusal) are made. No finding contradicts the specification's settled decisions.

**Readings, where the specification is silent:**
- A `step` event carries one field, `summary`: the lookup in words and its result in one line.
- Citation kinds are `event`, `fact` (the event that recorded it), `message` (an intent id), `reply` (its `reply_received` event) and `page` (the page key).
- A lookup names a lead in full or by the end of its id, so "lead 008" needs no queue lookup first.
- `lead_summary` shows the plan's open choices and `current_draft` shows its `intent_id`, so `record_ruling` and `edit_draft` can be proposed; the model sees no event id.
- `message_sent` reads "Sent the message to the producer": the payload does not hold the message kind.
- The endpoint refuses replay before any model call, so it handles no recording miss.
- The chat suite's first pass and fixture replies always replay, on a second runtime over the same database; only chat turns run in the suite's mode. The eval CLI replays only, so a record run is a host script that calls `evaluate_chat` in `record`.
- The first chat row of this milestone in `evals/results.jsonl` (commit f707881) is a replay run made before the recordings existed; every case reports a miss.

**Friction:** a builder in a worktree cannot commit (the worktree guard refuses its git writes), so the lead applies each builder's patch and commits it. Five builders ran in isolated worktrees; two returned no report text and the lead read their diffs.

**Next:** chat surface 2, the client.

## Chat surface 2: Client (06a5c06)

**Done:** the client half of `docs/chat-surface.md`. C2-A1 (the page test: lead 008 from "Load today's leads" to an approved packet inside its conversation, the cards of leads 000 and 003 in the queue conversation, a chip opening the panel), C2-A2 (`make check`) and C2-A3 (the fresh-clone rehearsal) pass, run by the lead. The lead also walked lead 008's path in a real browser against the running app in replay: load, the timeline, the delivered reply, Approve on the inline card, "Quote sent"; an example question answered with chips, and a chip opened the playbook page in the panel.
- Shell: the lead list (summary sentence, "Queue", three groups), the conversation, the drill-down panel and the demo controls in one grid; polling every five seconds that leaves a turn alone.
- Narrative (`web/src/conversation/`): assistant messages with a chip per bullet, bubbles for sent messages and replies, cards at the event that opened them, resolved cards as one line.
- Chat tail (`web/src/chat/`): turns by run and conversation in memory, the last four exchanges as history, live steps, numbered chips, cards on the lead they target, "Proposed on lead B", the composer.
- Panel (`web/src/panel/`): fact, event, message, reply, playbook page and the full lead view (waiting on, read-only; facts; plan; messages; the three lead actions).
- Demo controls: "Load today's leads" with a confirm when a run exists, "Deliver the producers' replies", the mode, seed and run id, minimisable.
- Server additions the client needed: `RunView.example_prompts`, `LeadDetail.pages`, `EventRow.choice_ids`.
- The replay attempt: the three example prompts were recorded once on the day as first loaded and replay cleanly in the keyless fresh clone, so replay answers an example asked first in the queue conversation and the buttons work in replay; the rehearsal asks all three. The composer stays disabled in replay.
- Documentation: architecture section 11, the proposals sentence and the `POST /api/chat` row; server-sent events leave the cut lists; the README walkthrough, run modes, cuts, limits and next steps.
- Deleted: `QueuePage.tsx`, `LeadDetailPage.tsx`, `ItemsSection.tsx`, `EventList.tsx`, `ChatPanel.tsx`; their tests are rehomed as the specification's table says.

**Not done:** Stand's wordmark and favicon. Fetching them from standinsurance.com into the repository was refused by the lead's permission system, so the left column shows the text "Stand" and the README has no line about the mark. Brett adds the two files or allows the fetch.

**Live calls:** one record run of the three example prompts on `deepseek-flash`: 7 calls, 2,877 in / 653 out. Jev: none. Chat-surface total with milestone 1: 27 calls, 25,447 in / 2,588 out.

**Checks:** at 06a5c06, `make check` is clean (766 fast Python tests, 107 web tests) and `tools/fresh_clone.py` passes with no keys (10 leads, the three example prompts answered from recordings with citations, 6 fixture replies accepted); `make test-slow` passed 33 at a7803ca. The reviewer read the milestone once: a failed poll cleared the chat tails (they are kept by run), one assertion of the replay test could not fail (the rule is the message alone; the lead and the history are in the recording key), and the demo confirm closed before its start answered; all three fixed, with its removals (a duplicate `leadId` prop, two exports, wording that named the replaced pages).

**Readings, where the specification is silent:**
- `EventRow.item_id` is set only for an underwriter's item, so a `blocker_opened` row with one is a card and a wait on the producer is a bullet; `choice_ids` matches a closed question card to its ruling.
- The plan is grouped by page on the server (`LeadDetail.pages`), which the page view and the playbook lookup share.
- In the narrative, what the system did with a reply (written under the `inbound` actor) joins the assistant's message; only the underwriter's rows stand apart. A run of more than three fact rows folds into "Recorded N facts". A resolved card absorbs the approval or ruling that closed it.
- A lead row and a conversation title show the short name ("Lead 008"); a chip in the timeline shows its event id.
- A bubble folds its body under its first line.
- The conversation column is 672px wide, so it stays clear of the demo controls at 1280px.
- In replay an example answers once per page load: a second question in the same conversation carries history, which has no recording.
- A click by element reference from the browser tool did not reach the example button; a click by position did. The page test clicks it through the DOM.

**Friction:** five client builders ran in isolated worktrees against a compiling skeleton with fixed props; none needed a prop changed. A module named `narrative.ts` beside `Narrative.tsx` breaks imports on a case-insensitive filesystem; the module is `narrate.ts`.

**Brett's ruling on the branding:** the name STAND in capitals, as text, stands in for the wordmark, and Stand's favicon is fetched from standinsurance.com at his request (`web/public/favicon.svg`: one rectangle and one path, no script or link); the specification's branding lines and a README line say so. At his request the buttons follow those of standinsurance.com, read from its stylesheet: a pill in ink (#131311) that lightens to #4a4842 on hover, or an outlined pill (#b5b3ac) whose border darkens, both pressing in slightly; the accent no longer colours the primary button. The two styles are defined once, in `web/src/index.css`. The conversation column takes the site's beige (#f3f1e6) with white cards, and the demo controls its black (#06080b), where the buttons turn white as on the site's dark sections.

**Next:** Brett's review of the surface.

## Chat surface: the UI pass (c65710d)

**Done:** the eight-point pass Brett approved (sent by the design session after a human look at the surface), with his one change: no colour changes, so the beige conversation and the ink-pill buttons stay.
- A lead's conversation leads with the answer: `LeadDetail.summary`, written by `src/uwh/api/summary.py` from the status, the open items, the plan and the asks ("This lead failed the fire simulation at 0.79. I need you to choose between a decline and legacy underwriting. Meanwhile I asked the producer for the 17 missing fields and am waiting for the reply."; a finished lead states its outcome and date). The underwriter's cards follow; the timeline folds under "Show the work (N steps)". The queue greets with "3 leads need you. 7 are waiting on producers."
- The log is cut: model calls, the rewrite checks, replay misses and faults are not narrated; a run of provider lookups is one line ("Looked up 6 providers: 2 found, 4 blocked on Date of Birth, City and Zip Code", from `EventRow.lookup`); repeated triage lines keep the last; chips are numbered within a message and appear only on fact lines and bubbles.
- Registry labels wherever a human reads a field: the narrative, the cards, the facts table and the panel (`labelKeys`, `fieldLabel` in `web/src/format.ts`).
- One decision per card: summary line, a folded preview of a draft with Edit inside, the choices as enabled buttons, one reason field after a choice with a confirm that repeats it.
- The column is centred at 720px; assistant messages carry an "Assistant" label; two text sizes.
- The lead list's chip says what differs ("Needs your decision", "Waiting on producer", "Quote sent"); the second line reads "Effective Jul 21 · in queue today"; the summary sentence left the sidebar.
- The example prompts sit beside the composer.

**Checks:** `make check` clean at c65710d (780 fast Python tests, 126 web tests). Screenshots of lead 003 and the queue were taken on the running app.

**Readings, where the pass was silent (agreed with the design session):**
- The summary line is written on the server; the queue greeting in the client from the run counts, with "K quotes sent." when any are.
- Narrative chips open only the fact view and the message or reply view; a card's "details" opens the full lead; chat answers keep a chip per citation.
- A committed decline is named by its playbook page and rule ("the post and pier page (PP-1)"): the plan holds no decline reason text.
- Inside the fold an open item is its event's line; its card sits above the fold. Only the underwriter's items are cards above the fold; a producer or data wait is in the summary line.
- "Show the work (N steps)" counts the lines the fold shows, a folded run as one.
- The age reads "in queue today" under half a business day, else whole days.
- An option button reads capitalised ("Legacy underwriting").

## Chat surface: notes, the Full detail link and the request's number (e2f34d0, 53b2135 and after)

**Done, at Brett's direction:**
- A note is optional on every underwriter action: the structured choice (approve, reject, the option chosen) is the captured decision and the note is context, with a placeholder per action. Two keep a required reason, labelled "Reason for the decline, kept on file": declining a lead and approving a decline notice, which the command layer refuses without one. Edit carries no note. Architecture section 12 and the README say so; `RejectPayload` and `RecordRulingPayload` accept an empty `reason`.
- The "Full detail" link goes while the panel shows that lead's full detail and returns when it closes.
- A request's opening and closing agree in number with its asks: the rewrite prompt receives `ask_count` and says "a detail" for one and "a few details" for several, with "one reply covering the items" only for several; the rendered fallback is count-aware the same way (`OPENING_ONE_ASK`); the judge treats an invitation to ask questions ("let us know if anything is unclear") as warm wording. Lead 009's request reads "There is just one thing we still need before we can finish the quote. … Thank you for your help with this." (Brett found "we just need a detail from you" awkward, so the prompt asks for natural words and the fallback reads "There is one thing we still need before we can complete the quote."; the one-ask closing only thanks, since the judge treats "a quick reply by email is all we need" as a request.)

**Live calls:** the wording was recorded three times in all: two rounds on the first prompt (below) and one on the natural wording, 23 `polish_message` calls, 8,509 in / 1,847 out, with three multi-ask rewrites rejected by the judge and falling back, plus the chat suite (9 calls) and the examples (7 calls, 1,341 in / 629 out) again. Before that, the prompt change moved the recording keys, so the seed-42 pass and the fixture replies were recorded once more on `deepseek-flash`: 22 `polish_message` calls (both rounds), 4,975 in / 1,594 out, and 6 `read_reply` calls, 1,046 in / 2,078 out, whose recordings came back byte for byte the same; no rewrite fell back. The chat suite (9 calls, about 6,500 in / 900 out) and the three example prompts (7 calls, 1,334 in / 659 out) were recorded again, since their lookups read the request text. An earlier pass-only record run (18 calls, 12,258 in / 1,311 out) was superseded when the round-two rewrites of the replies turned out to need recording too. Jev: none.

**Checks:** `make check` clean (782 fast Python tests, 128 web tests); `make test-slow` 32 passed; the seed-42 eval row passes every grader; the keyless fresh-clone rehearsal passes with the three example prompts.

**Readings:** every recorded rewrite now passes both checks, so the three tests that pinned lead 001's rejected rewrite lost their subject and are deleted; the fallback is pinned by the scripted tests of `polish_message`, and M5-A3 names them. A recording of the chat suite or an example made before the pass was re-recorded is an orphan and was removed.

**The panel as a layer (design session):** the drill-down panel overlays the conversation column, which keeps its width and place; it is as wide as its content, up to 60% of the viewport (at least 360px), with a shadow on its left edge, and nothing in it scrolls sideways: the facts table is fixed-layout with wrapping cells and the message bodies wrap. The two fixed widths (360px, 480px) are gone from the code and the specification. Brett then found it wider than it needs to be: the maximum is 700px, and while the panel is open the conversation column moves to the left of its area. An open panel follows the lead the underwriter selects next; opening the queue leaves it on the last lead.

**Event view and title (Brett):** the panel's event view is the lead's whole timeline with the cited event expanded in place (type, actor, time, mode, sentence, and the field, lookup or message it carries); a click on another row moves the expansion, and the previous and next links are gone. The conversation title sits over the content column, so it is centred with it and moves left with it while the panel is open.

**Citations and kinds (design session):** a number is a citation, so only the assistant's answers carry numbered chips, each with a source line under the answer (`Citation.text`, written by the lookup that numbers the item, with the registry's label for a fact); the narrative's chips are labelled by kind ("fact", "email", "reply"). The panel shows no database id: the timeline's expanded event is headed by its sentence, and the fact view's source link reads "Recorded <time>". The lookup results the model sees did not change, so no recording moved.

**Timeline button (design session):** "View event timeline" sits under a lead conversation's opening message and opens the panel's event view on the latest event, since the view expands one event; the queue conversation has none.

**State colours (design session, approved by Brett):** three `Badge` variants, `needs` (accent on a 10% tint), `waiting` (grey) and `done` (`--done`, #335c3e, on a 10% tint), used by the lead list's chips, its "Waiting on the underwriter" header with a "Needs you · N" count, the cards' "Waits on" tag and the full lead view; a card that needs the underwriter has a 3px accent left border, and the greeting's count is in the accent. Contrast: the accent on its tint is about 11:1 and the green about 6.6:1; the grey text is Stand's #4a4842 (the primary hover token), since the muted grey fell under 4.5:1.

**Cross-lead questions (design session):** `queue_facts` reads every lead of the run at once (status, what it waits on, the fields named in `keys` or the address fields), cited by lead; a turn's last of eight steps offers only `answer` and `propose_command` (`final: true`), so the model answers from what it has, and `NO_ANSWER` names the leads it read; a lookup repeated with the same arguments is not run again. The prompt and tool schema moved the recording keys: the chat suite (now five cases, with "Which leads are in Florida?" answered from the queue facts) and the examples were recorded again, 21 recordings, 19,617 in / 1,922 out. Live, from the queue: "tell me about the properties in Europe" read the country field of all ten leads and answered that none is recorded and the addresses are in CA, OR, CO and FL; "which leads are in Florida" named 004, 007 and 009, each cited.

**Shaped answers (Brett):** the prompt asks for an answer shaped for reading (a blank line between paragraphs, one "- " line per listed item, no other markup) and the chat tail renders paragraphs and lists (`AnswerText`). The suite and the examples were recorded again on the changed prompt: 27 recordings, 21,590 in / 2,391 out.

**The needs chip (Brett):** the tinted accent chip did not stand out, so the `needs` variant keeps the accent text on its tint and gains a 1px accent outline (Brett found the solid fill too dark); the token is unchanged. The left column is 340px, so "Waiting on the underwriter" and its count fit on one line; the Queue entry reads as the hub (bold, a home mark, a rule beneath).

**Finished states (Brett):** a quote sent keeps the green and a lead declined takes a muted slate (`--declined`, #3f4f6f, about 7:1 on its tint), a fourth `Badge` variant, so the three outcomes of a lead read apart.

## Chat surface: the UI audit (4e6d8af to 1e2cba8)

**Done, at Brett's direction** (from an audit of the UI against published underwriting-workbench, queue and human-in-the-loop guidance; three builders in isolated worktrees, the lead merging each):
- A choice card's values carry what the page's graph makes of each (`LeadDetail.readings`, `src/uwh/api/readings.py`, reusing the graph's case matching through `matching_case`): "Fails: above 0.50", "Declines", "Passes", "Passes only if the client will mitigate", "Your call: the playbook sets no threshold" (I16) or "…does not settle it" (I14, I15). No threshold is invented. The readings are computed for the view and are no part of the hashed plan, so no recording moved.
- A draft's approve button names what it sends ("Send decline notice", "Send quote", "Send request"), so approving a decline notice does not read as approving the lead; a decline and sending a decline notice are accent-outlined (`.button-destructive`); a card drops the "Waits on" tag its kind already implies.
- Values read Yes/No and "Not provided", a date field as a date; a lead id drops the seed ("LEAD-003"). Stand's registry labels the date field `property_purchase_date` "Purchase Year"; the label stays Stand's.
- A lead row's chip says what differs (`QueueRow.decision`, the open request's asks and round) and a producer-waiting row says when its request went out; a lead with a request out shows its round, send time, asks (`DraftView.asks`, labels: a field, a question, or "Confirm <field>" for a confirmation) and a link to the message.
- Full detail groups facts under the registry's sections (`FactField.section`; catalogue questions under "Questions", the contact email under "Contact"), shows a source tag only when it is not Submitted, and lists the missing fields first, grouped by the triage's resolution (`LeadDetail.missing_fields`), so the producer's asks read apart from fields the system looks up.

**Readings:** "in queue today" stays for leads not waiting on a request; the "ago" on the request card uses `run.sim_now` as last fetched. A row's ask count is the lead's distinct asks across its requests, as `ask_count` was.

**Live calls:** none; the chat suite replays unchanged (6 passed).

**Checks:** `make check` clean (818 fast Python tests, 161 web tests).

**Friction:** this shell's PATH has Homebrew's Node 25 without pnpm; `make check` runs with `~/.nvm/versions/node/v22.23.3/bin` first on PATH. Builders in worktrees could not run the pnpm steps and ran `tsc`/`vitest` through a temporary `node_modules` link.

## Chat surface: the seed, single tags and reasons (6a54ca9 and after)

**Done, at Brett's direction:**
- No reader sees the run's seed in a lead id: a lead with no address is labelled "LEAD-000" (`without_seed` in `src/uwh/skills/steps.py`), so the decline notice's subject reads "Regarding your submission: LEAD-000", and a chat answer's lead ids are shortened before the underwriter reads them. The model still reads full ids, so the commands it proposes keep naming leads in full.
- Full detail's "Waiting on" tags an item once, by its kind, coloured by who it waits on; `OWNER_LABELS` had no other reader and is gone.
- A decision carries its reason. A decline is explained by the values on its path through the page's graph (`decline_reason`), in the lead's opening line, the finished "Declined on …" line and the decline notice card ("Why: …"); the line asks the underwriter to send the decline notice or withdraw it, and a ready packet to be sent, matching the buttons. The narrative's plan sentence names the committed effects and a choice left open ("Built the action plan: a decline (PP-1)"). An edit with no note no longer ends in a stray period. This replaces the page-and-rule-only reason ("the post and pier page (PP-1)").

**Live calls:** the chat suite and the three example prompts were recorded twice, since their lookups show the label and then the event sentences: 16,241 in / 5,394 out and 14,698 in / 5,425 out for the suite, 9 calls each for the examples (7,303 in / 840 out, then 1,935 in / 893 out as logged). Jev: none.

**Checks:** `make check` clean (829 fast Python tests, 163 web tests).
