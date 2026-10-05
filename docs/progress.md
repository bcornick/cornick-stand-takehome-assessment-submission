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
