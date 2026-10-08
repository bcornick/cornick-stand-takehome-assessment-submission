# Design spec: underwriting triage on a skill-and-eval harness

This document is the single authority for the build. Where another file disagrees with it, this document wins. Findings from `docs/build_logs/critique.md` are dispositioned in section 16.

## 1. Objective

Take the morning queue of ten property leads produced by Stand's lead generator and drive each lead to one clean next action, with the underwriter in control of every consequential decision:

- a quote packet goes out, or
- one clear follow-up message goes out, or
- the lead waits on a named human decision that is visible in the underwriter's queue.

The third state departs from the brief's two end states on purpose. Lead 000 is the worked example: its confirmed facts decline on every path, so sending its producer more than 25 questions would waste the producer's time. It waits for the underwriter to approve the decline, and a decline notice then goes out.

The submission reads as a small harness with underwriting triage as its first vertical. It is not one agent.

## 2. Background

### 2.1 What Stand provides

| Item | Location in this repo | Notes |
|---|---|---|
| Brief | `docs/brief/agentic_uw_takehome.md` | Five product decisions, four deliverables |
| Field registry | `docs/brief/field_registry.json` | 73 fields: 52 always, 18 conditional, 3 bind-only |
| Lead generator and mock mailbox | `sim-harness/` | Stand's code, unmodified |
| Underwriting playbook | `docs/playbook/` | 13 FigJam pages transcribed to Mermaid with reading notes. The screenshots its README mentions are not shipped; the board link in that README is the visual reference. |

### 2.2 Facts about the harness that shape the design

Each fact was checked against the code.

- **Queue.** `POST /queue?count=10&seed=42` builds a deterministic queue. `POST /queue` deletes any stored queue. Startup alone creates no queue.
- **Lead construction.** Each lead is built clean, then archetypes mutate it, then a perturbation pass nulls fields by tier rate and may inject one conflict. A guarantee pass can add an archetype after perturbation; it does not fire for ten mixed leads under the supplied config.
- **Seed 42 archetypes.** `occupancy_conflict` (two leads), `post_and_pier`, `profile_kyc` (three leads), `wildfire_severe` (two leads). No rural protection class, replacement cost gap, electrical, trust, plumbing or pool archetype appears, so the pages those archetypes would reach are not built (section 4.1).
- **Answer key.** `GET /leads/{id}/debug` returns the generator's mutation history: difficulty, archetypes, and one record per touch (a field can carry two). It is not an oracle. It marks inactive conditional fields as missing, omits fields that become required after an archetype, and files derivable classes as system-owned nulls.
- **Mailbox.** `POST /emails` is an unconditional insert. Metadata round-trips only through `GET /leads/{id}/emails` and `GET /emails/{id}`. Row ids keep increasing after `POST /reset`. No reply endpoint exists.
- **Ports.** Both services listen on 8080 inside the compose network. Stand's compose file maps them to host ports 8081 and 8025 and binds one shared `./data` folder.
- **Clock.** The generator's reference morning is Monday 2026-06-29 08:00 UTC. Leads arrive up to 180 minutes before it. The mailbox stamps wall-clock time.
- **Registry validation.** `shared/registry.py` checks types and select membership only. It accepts out-of-range numbers and any string as a date.
- **Registry conditions.** `requiredWhen` is prose in six forms. `None` in `pool_type != None` is the option string, not null. Protection class options are strings while the condition writes numbers. Six conditional fields carry no `requiredWhen`.
- **Recipients.** `source` is one of `agent_portal`, `broker_email`, `direct_web`. The registry has no producer contact field. `owner_email` is bind-only.
- **Example payloads.** The two copies differ in one value: `kyc_score` is 82 in one and 8 in the other. The generator uses 1 to 10.

### 2.3 Answers from Stand's clarifying call

- The review session is 45 minutes.
- The submission should read as a harness.
- One message per lead at a time.
- "A quote goes out" is a final state. No pricing is expected.
- Stand runs the same seed (42).
- Any model or framework is acceptable. Stand supplies its own API key through an env file.
- The submission must run on any device and operating system.

## 3. Goals

1. One command starts everything in containers.
2. Every seed-42 lead reaches one primary next action, with all blockers visible.
3. Rules live in data files read by a small interpreter, not in prompts. An underwriter's ruling on a choice is recorded and applies to that lead.
4. Models are used only where language must be read: reply extraction, reply classification, and the chat.
5. The eval loop grades stored state (mailbox, event log, fact ledger), proves its graders can fail, and logs every run.
6. Every capability is a skill with a typed contract and its own eval cases.

## 4. Non-goals and cut line

- No pricing or rating.
- No reply simulator. Reply handling is real; reply text comes from fixtures or a paste box.
- No live third-party data calls. Addresses are synthetic.
- No agent framework and no model-driven control flow outside the chat.
- No learned decision model. The rules are written down.
- No rule editor. The rules change by a reviewed commit to `src/uwh/rules/data/`.
- No promotion of autonomy from eval evidence. The levels are constants in code (section 7.4).
- No model-written questions. Emails are rendered from the ask plan by code; the model writes only an opening and a closing (section 10.2).

### 4.1 Cut line

The brief sets a 5 to 6 hour box and says the choice of what to cut is evaluated. One scope is built: the list under "What is built" in `docs/build_logs/plan.md`. The README lists each item below under "Cut and why".

Not built:

- **The five playbook pages no seed-42 archetype reaches: Plumbing, Electrical, Pools, Trusts & LLCs, and Protection Class 9 & 10.** Their interpretation rows, catalogue questions, wording and resolution rules are not in the data files. Seven pages are built: Profile, Occupancy, Fire Simulation, Roof, Siding, Post & Pier and Replacement Cost. A lead that a not-built page applies to carries an explicit `not_evaluated` note naming the page, never a silent pass (section 9.6). Plumbing and Electrical apply to every lead, so each lead, and lead 008's quote packet, carries a note that those two pages are not evaluated.
- **The MCP transport.** The chat calls the same functions directly.
- **The 50-seed sweep.** The system and its evals run seed 42 only.
- **The rule-change flow and the model-driven triage comparison.** Rules change by a reviewed commit to the data files.
- **The settings screens, the skills screen and the emergency stop.** Autonomy levels are constants in code (section 7.4).
- **Controls and graders beyond those section 13 names.** The eval has three controls: do nothing, email everything and send twice.
- **The constructed packet cases and the outcome-case sample.** Cases are a table per page.

## 5. Scenarios

Seed-42 leads, read from the stored queue. Expected first-pass results are fixed by the labels under `evals/labels/seed42/`; this table is orientation.

| Lead | Notable facts | Expected first pass |
|---|---|---|
| 000 | Pier foundation supporting living area; primary home unoccupied 8 months; no address | Proposed decline for the underwriter. No producer request. |
| 001 | No street address; several lookups blocked on it | Routine request including the address. The fire probability lookup is blocked, so the Fire Simulation page is undecided and raises no card. |
| 002 | KYC 8 | Request for missing fields; liability exclusion carried to the quote |
| 003 | Fire probability 0.79; wood shake siding; primary home unoccupied 3 months | One underwriter card (failed fire simulation). A routine request with the registry asks and the occupancy confirmation is drafted and held for the underwriter while the choice could decline the lead: the underwriter sends it, or declines and it is withdrawn. Mitigation questions are held until the choice is made. The Occupancy page is undecided while the conflict is open. The Siding requirement (wood shake, fire probability above 0.50) is committed. The four protection-class questions are blocked, not asked. |
| 004 | Zero residents on an owner-occupied home; animals | Routine request with a confirmation question |
| 005 | KYC 6; zero residents; pool type missing | Routine request with a confirmation; liability exclusion carried to the quote; and follow-on questions for the missing pool fields only; the diving-board answer already on the lead is not asked again. |
| 006 | Fire probability 0.89; wood shake siding; roof material missing | One underwriter card (failed fire simulation). A routine request with the registry asks, including roof material, is drafted and held for the underwriter while the choice could decline the lead: the underwriter sends it, or declines and it is withdrawn. Pool values already on the lead are not asked again. The Siding requirement is committed. The four protection-class questions are blocked, not asked. |
| 007 | KYC 9 | Request for missing fields; liability exclusion carried to the quote. The four protection-class questions are blocked, not asked. |
| 008 | Two missing fields | Routine request. With the full-reply fixture, this lead reaches an approved quote packet: the demo case. |
| 009 | One missing field; animals | Routine request |

Other scenarios the system must handle, covered by fixtures and hand-written cases:

- A partial reply produces one consolidated second request.
- A reply contradicting a submitted value goes to review.
- A reply containing instructions aimed at the system changes nothing.
- A crash between send and record produces no second email.
- A reply that restates a conflicting value closes the conflict.
- A failing `read_reply` skill hands the reply to the underwriter unread.

## 6. System overview

```mermaid
flowchart LR
    subgraph Stand harness, unmodified code
      LG[leadgen :8080]
      MB[mailbox :8080]
    end
    subgraph App container
      API[FastAPI: REST]
      CMD[Command layer: policy, autonomy]
      RT[Runtime: lead workflow, waits]
      SK[Skills]
      RC[Rules core: triage, validators, graph interpreter]
      PR[Stand-in providers]
      DB[(SQLite: events, facts, intents, approvals)]
    end
    UI[React queue surface + chat] --> API
    API --> CMD --> RT --> SK
    SK --> RC
    RT --> PR
    SK --> CMD
    CMD --> MB
    RT --> LG
    CMD --> DB
    RT --> DB
    EV[Eval runner] --> DB
    EV --> MB
```

### 6.1 Repository layout

```
compose.yaml              one launch file; services and profiles are listed in section 14
.env.example              the seven variables listed in section 14
sim-harness/              Stand's code, unmodified
src/uwh/
  runtime/                events, facts, workflow, waits, commands, policy
  rules/                  registry triage, condition parser, validators, interpreter
  rules/data/             graphs/*.yaml, interpretation.yaml, catalogue.yaml, derivations.yaml
  providers/              stand-in lookups and the world fixture reader
  skills/<name>/          manifest.yaml, skill.py, cases/, prompt.md (model skills)
  api/                    REST
  chat/                   chat tool loop
evals/                    runner, graders, controls, labels/, results.jsonl
fixtures/replies/         reply bodies for the fixture-reply control
recordings/               model exchanges for replay mode
tools/                    capture_world.py and other offline scripts
web/                      Vite + React + TypeScript + shadcn/ui
tests/                    mirrors src/
docs/                     this file, critique, plan, progress, brief, playbook
```

### 6.2 Stack

- **Backend:** Python 3.12, `uv` with a lockfile, FastAPI, Pydantic, SQLite, pytest, ruff, mypy.
- **Frontend:** pnpm, Vite, React, TypeScript, shadcn/ui, built inside the container to static files that FastAPI serves.
- **Models:** DeepSeek V4.1 Flash (`deepseek-flash`), an open-weights model, through DeepSeek's Anthropic-format endpoint (`https://api.deepseek.com/anthropic`) with the Anthropic SDK. `MODEL_API_KEY`, `MODEL_BASE_URL` and `MODEL_ID` configure it. Structured output is a forced tool call: one tool whose input schema is the output model's JSON schema, `tool_choice` naming that tool, thinking disabled, and the tool input validated with Pydantic. Every forced-tool call sends `thinking` disabled. `messages.parse()` is not used; the endpoint ignores its output format. Jev (`jev-1.13.0`, TypeSafe SDK) answers reply classification first when its key is set, with the language model as the fallback.
- **Stand's harness** keeps its own Python 3.11 images.

## 7. Runtime

This is an underwriting tool, and the runtime uses underwriting names directly: its statuses, blocker kinds, blocker owners, message kinds, item kinds, observation sources and actors are the ones this section and Appendix A give, and the ruling kinds and review causes are the ones the stage 2 contracts fix. Each of these value sets is defined once, in `src/uwh/runtime/event_types.py`, the request kinds among the message kinds and the autonomy levels included; the run mode alone is defined in `src/uwh/settings.py`, which reads it. `src/uwh/skills/vertical.py` holds what is built on those names: the status transitions and terminal statuses, the blocker priority order, the command classes, the review causes that persist, the rule for a blocker the lead detail view can serve, `confirmation_only_class`, the reference morning, the order of the workflow's steps and the effect of `approve` and `reject` on each item (A.11).

### 7.1 Lead workflow

A lead has a **status** and a **set of open blockers**. Statuses: `received`, `triaged`, `in_progress`, `quote_sent`, `declined`. Blocker kinds: `producer_reply`, `underwriter_review`, `underwriter_question`, `data`, `delivery_unknown`.

- A lead's steps run in order. Leads run concurrently with a bounded pool.
- One waiting primitive: a blocker row with a kind, an owner and a resume trigger. A lead may hold several blockers at once.
- The **primary next action** shown for a lead is its highest-priority open blocker, in the order `delivery_unknown`, `underwriter_question`, `underwriter_review`, `data`, `producer_reply`. Terminal leads have none.
- Any accepted new fact re-evaluates the lead.
- A step that fails rolls back its own writes and opens a `data` blocker on the lead. A lead holds at most one open step-failure blocker, so a repeat failure opens no second one, and the blocker closes when a later pass on that lead completes.
- At startup, after intents are reconciled (section 7.5), the pass of every lead in `received` or `triaged` that has no open blocker, or only a step-failure `data` blocker, is run again. A run left in `processing` is then marked `settled`, so a new run can start. Every other lead keeps the state it had reached.
- With no API key in live mode, a delivered reply is recorded unread and raises an underwriter review.

### 7.2 Event log

Append-only table. Each row: id, lead id, run id, event type, payload, actor, ruleset hash, prompt versions, model id and request id where a model was called, real timestamp, simulated timestamp. A command can arrive before any run exists (a refused command); its events carry the fixed run id `pre-run` and the reference morning as their simulated time, so no event has an empty run id.

### 7.3 Fact ledger

Two layers.

- **Observations.** One row per reported value: field or catalogue question id, value, source (`submitted`, `fetched`, `derived`, `assumed`, `reply`, `underwriter`), evidence (quoted span, provider name, derivation id, interpretation row id), status (`accepted`, `pending_review`, `rejected`).
- **Effective facts.** The selected value per field, pointing at its observation. Selection follows source authority:
  1. An underwriter ruling outranks everything. `resolve_fact` leaves no conflict open on its key, even one its value trips, and a validator does not reopen a conflict on the same values (a later change to the other field of a pair opens one again); `resolve_fact` also rejects the open `pending_review` observations on its key, so an older reply value cannot replace the ruling.
  2. A reply value fills a missing producer-editable field directly, and replaces an `assumed` value the same way.
  3. A reply value that differs from an existing submitted, fetched or underwriter value is `pending_review` and raises an underwriter review; the existing value stays in force until the underwriter approves or rejects. A value that also trips a validator follows this rule and opens no conflict.
  4. A reply never sets a system-owned field.
  5. A derived fact is recomputed when its input changes.
  6. A reply that restates a value under an open conflict closes the conflict, records the reply as evidence and marks the fact confirmed. A reply that changes either field of a conflicting pair follows rule 3.
  7. A reply value that differs from an accepted value from an earlier reply is `pending_review`.
  8. A reply value that trips a validator is accepted and opens the conflict; its confirmation goes in the next request.
  9. A reply to a round that has closed is recorded, raises an underwriter review and increments the lead revision, so a pending approval on that lead returns to review. Its values are recorded `pending_review` and applied to nothing; the review names the intent the reply answered, and acknowledging the review marks those values rejected. The values reach the facts only through `resolve_fact`.
  10. The underwriter settles a `pending_review` observation raised under rule 3 or rule 7 with `approve` (it becomes the effective fact) or `reject` (the existing value stays), and can supply or correct any fact with `resolve_fact`.

Derived facts and decisions record the fact ids and rule versions they used. A changed effective fact marks its dependants stale. Stale drafts and approvals return to review. A sent message is history and is never undone.

### 7.4 Command layer

Every state-changing action is a typed command. The workflow, UI and chat all submit commands; nothing else writes.

**Actors.** `workflow`, `underwriter` (the local user of the UI), `assistant` (chat), `inbound` (the reply endpoint). Identity comes from the transport, never from model arguments.

**Autonomy levels.** Autonomy levels are constants in code (`COMMAND_CLASSES` in `src/uwh/skills/vertical.py`). A routine request sends automatically and every other message waits for the underwriter's approval, except that a routine request also waits while an open underwriter choice could still decline the lead (`choice_can_decline`), so a producer is not asked about a lead the underwriter may decline; the underwriter can send it at any time, a decline withdraws it, and once no such choice is open the next draft sends itself. Rejecting a request discards it unsent, and no request is drafted again until the lead changes (a ruling, a resolved fact, a reply); a request that is the lead's only open item cannot be discarded, since the lead would be left with nothing to decide. A quote packet is not rejected from its card: saying no to a quote is declining the lead, which withdraws the packet. `auto` runs without a person; `review` needs an underwriter approval.

| Command class | Level | Who may submit |
|---|---|---|
| `fetch_data` | auto | workflow |
| `send_routine_request` | auto | workflow |
| `send_sensitive_request` | review | workflow |
| `send_quote_packet` | review | workflow |
| `send_decline_notice` | review | workflow |
| `deliver_reply` | auto | inbound, underwriter |
| `approve`, `reject`, `edit_draft`, `resolve_fact`, `decline_lead` | human only | underwriter |
| `record_ruling` | human only | underwriter |
| `start_run` | human only | underwriter |
| `propose_command` | auto | assistant |

- `assistant` can read and can propose. A proposal becomes a command card that the underwriter applies. They cannot approve. A proposal carries one of `edit_draft`, `record_ruling`, `resolve_fact` and `decline_lead`: asked to approve or reject, the assistant points the underwriter to the item instead.
- **Approval binds to a frozen artifact:** lead revision, action-plan hash, ruleset hash, recipient, and the exact message or packet hash. The dispatcher rechecks all five and the class's level immediately before sending. A mismatch returns the item to review. An `approve` of a draft carries the payload hash of the artifact the underwriter was shown; a hash that is missing or not current is refused, so a stale browser cannot approve replaced content.

### 7.5 Sending

Sending is a runtime primitive, not a skill.

An intent moves through `draft → dispatching → sent`, or `dispatching → unknown`.

1. A message is created as an intent in state `draft`: run id, lead id, round, message kind, recipient, subject, body, ask ids, payload hash. `edit_draft` replaces the subject, body and payload hash of a draft and voids any approval of it. An edited `routine_request` becomes a `sensitive_request`, so it waits for approval; a quote packet or decline notice keeps its kind.
2. Dispatch commits the state `dispatching` in its own transaction. The post starts only after that commit and runs outside any transaction. From the commit on, the intent is immutable.
3. Post to the mailbox with the intent id, run id, kind, round and payload hash in `metadata`. Record the returned mailbox id and set the state to `sent`.
4. On any ambiguous result, list `GET /leads/{id}/emails` and match the intent id. A match is recorded as `sent`. No match sets the state to `unknown` and opens a `delivery_unknown` blocker for the underwriter.
5. At startup, every intent in state `dispatching` is reconciled by step 4 before any dispatch. Drafts are left alone.

Resolving `delivery_unknown`: `approve` on the item re-runs step 4. `reject` closes the intent as not sent; the workflow then creates a fresh draft for the same round, which waits for approval whatever its class.

The promise is **no automatic resend after an ambiguous delivery**. The mailbox has no idempotency key, so exactly-once delivery is not claimed. One sender per lead at a time. Rounds number requests only: the first request is round 1. A quote packet or decline notice carries the round of the last request, or round 0 when the lead has had no request, and does not count toward the two-round limit. A duplicate is more than one request in the mailbox for one (run id, lead id, round), or more than one quote packet or decline notice for one (run id, lead id). Fixtures and tests key on lead id and intent id, never the mailbox row id.

### 7.6 Clock

`sim_now = reference morning + (real now - run start)`. Lead age and deadlines use `sim_now`. Events store both timestamps. Business days are counted in UTC, Monday to Friday.

### 7.7 Run modes

- **live:** model calls use the key from `.env`.
- **replay:** model calls are served from `recordings/` keyed by skill, prompt version and input hash. A miss fails closed with a visible error, except a Jev call (10.4): its miss is recorded as a `replay_miss` event and the language model classifies the reply. The input hash covers only the content the model is shown (for `read_reply`, the reply body and the open asks), never run ids or intent ids. The prompt version is the hash of the `prompt.md` bytes and of the forced tool (its name, description and input schema), so a change to either records again. After any change to a `prompt.md` or a tool, the affected recordings are recorded again and committed. Replay uses its own app database.
- **record:** a live run that also writes each model exchange to `recordings/` at the repository root, bind-mounted read-write in this mode and read-only in replay. Recordings are committed.

The mode is shown on screen at all times and stored on every event. The system never falls back from live to replay.

## 8. Skill contract

A skill is a folder under `src/uwh/skills/`:

| File | Content |
|---|---|
| `manifest.yaml` | name, version, purpose, trigger, command classes it may issue, fallback when unavailable, pass threshold (only for a skill with `cases/`) |
| `skill.py` | one entry point `run(input) -> output` with Pydantic input and output models; output is a result or a typed abstention |
| `cases/` | eval cases: input, expected output or expected properties; only for a skill that has a pass threshold (`evaluate_playbook`, `read_reply`) |
| `prompt.md` | model skills only; the version is the hash of the file and the forced tool |

Rules:

- The skill list is a plain list in code. A test fails when a folder lacks any part. `cases/` is a part only of a skill whose manifest has a `pass_threshold`; the other skills are covered by plain unit tests and the seed-42 graders.
- A write that issues a command class refuses one the issuing skill's manifest does not declare: `create_draft` for the send classes, the resolve step for `fetch_data`.
- **Status.** The eval runner writes `skill_results.<name>: {cases_passed, cases_total, passed}` into each `run` row, computed from the skill's `cases/` against its manifest threshold, for the skills that have cases. A model skill uses its fallback when the model is missing, a recording is missing in replay, or its answer is rejected; the runtime does not read the results log.
- `unavailable` applies in live mode with no key. Replay mode needs no key and runs model skills from recordings.
- **What makes this a harness:** a skill added with a manifest, and cases with a threshold where it has them, is dispatched and permission-checked with no runtime change, and the eval runner scores its cases on every run.

| Skill | Model | Fires when | Fallback |
|---|---|---|---|
| `triage_fields` | no | lead received or facts changed | none (deterministic) |
| `resolve_data` | no | a field's resolution is derive, fetch or assume | none |
| `evaluate_playbook` | no | after resolution | none |
| `plan_asks` | no | after evaluation | none |
| `render_message` | no | an ask plan, quote or decline needs a message | none |
| `polish_message` | Language model | a request has been rendered | the rendered request is used as it is |
| `read_reply` | Language model for extraction; Jev first for classification when its key is set, language model as fallback | a reply is delivered | reply goes to the underwriter unread |
| `build_quote_packet` | no | no open blockers and no asks remain | none |

The chat is governed the same way: its lookups, prompt and eval cases live in `src/uwh/chat/` with a manifest.

## 9. Rules core

### 9.1 Source precedence

| Concern | Authority |
|---|---|
| Which fields exist, who owns them, what must be collected | Field registry |
| Underwriting logic | Playbook detail pages |
| List of criteria | Playbook overview page; where it disagrees with a detail page, the detail page wins |
| Derivation maps (roof class, siding class) | The maps in Stand's `generator.py`, copied into `derivations.yaml` with the source cited |
| Anything the above leave open | `interpretation.yaml`, one row per gap (section 9.7) |
| Board notes that conflict with the registry's collection rule (pool "assume no", occupancy "quote without this") | Registry wins for collection; the note is cited in the row |

### 9.2 Field triage

For each field the join of lead and registry yields:

- `value_status`: `present`, `missing`, `conflicting`, `unsupported`
- `requirement`: `required`, `conditional_active`, `conditional_inactive`, `conditional_unknown`, `bind_only`, `optional`
- `resolution`: `none`, `derive`, `fetch`, `assume`, `ask`, `ask_follow_on`, `defer`, `verify`, `not_required`, `blocked`
- `depends_on`: field ids

Rules:

- JSON null means missing. `"None"`, `false`, `0` and `"Unknown"` are present values.
- Conditions are parsed by a small parser covering the registry's six forms, comparing against option strings, with three results: active, inactive, unknown.
- A present, non-conflicting value needs no ask, whatever its condition.
- `conditional_unknown` on a missing producer-editable field whose controlling field is producer-editable yields `ask_follow_on`: the question is worded conditionally in the same message ("If there is a pool: is it fenced?"). `wording.yaml` holds one conditional preamble per `requiredWhen` form that a follow-on question can take (A.7); `is_gated_community`, which has no `requiredWhen`, is asked with no preamble.
- When the controlling field is system-owned and unresolved (its lookup is blocked or pending), the dependent field's resolution is `blocked`: no ask. It is asked in the next round only if the resolved value activates the condition. This covers the four fields conditional on protection class 9 or 10.
- Missing system-owned fields never yield `ask`. One whose lookup returns `blocked` has resolution `blocked`; labels use the same definition.
- `bind_only` yields `defer`.

Conditional fields with no `requiredWhen`:

| Field | Rule |
|---|---|
| `broker_tier` | fetch |
| `has_primary_policy_with_stand` | fetch |
| `replacement_cost` | fetch |
| `listed_for_sale` | ask when missing |
| `is_gated_community` | A three-valued condition. Inactive when `pool_type` is known and not Inground, or `pool_security` is Fenced. Active (ask) when `pool_type` is Inground and `pool_security` is known and not Fenced. Unknown (follow-on) otherwise. |
| `opening_protection` | never ask; no playbook page uses it |

### 9.3 Resolving a missing value

Order of precedence:

1. An accepted observation.
2. A derivation whose inputs are present. Roof class and siding class are derived only, never fetched. For these two fields the derivation from the effective material outranks a submitted class; the submitted class is kept as an observation and used only while the material is missing.
3. A provider lookup, for system-owned fields.
4. A stated default, tagged `assumed`: `protection_class` is "9" when the provider returns not found.
5. Otherwise ask (producer-editable) or raise a `data` blocker (system-owned, provider unavailable).

### 9.4 Stand-in providers and world values

`tools/capture_world.py` runs Stand's unmodified generator with a recording wrapper on `_base_lead` and on each archetype call, asserts the wrapped output equals the unwrapped output, asserts no guarantee-pass archetype fired, and writes the provider fixture for the seed. The fixture is captured for seed 42. The fixture is synthetic provider data, not ground truth. It replays the generator's state before perturbation, which keeps values such as replacement cost consistent with Coverage A; the README states this plainly. Each fixture entry stores a fingerprint of the lead's submitted fields. On a missing entry or a fingerprint mismatch the provider returns `unavailable`, which opens a `data` blocker for the lead; no value is made up. The seed is read from the environment (`SEED`, default 42). The application reads only this fixture. It never calls the debug endpoint; the leadgen service passes `DEBUG` through, off by default (section 14), and the leadgen client has no debug method.

Provider result: `{status, value, source, fetched_at}` with status `found`, `not_found`, `blocked`, `unavailable`. A blocked result names the missing input fields.

| Field | Provider inputs | Returned when the lead's value is missing | Real source this stands in for |
|---|---|---|---|
| `broker_tier`, `has_primary_policy_with_stand` | lead id | clean base value | Stand's own policy and distribution systems |
| `replacement_cost` | full address | clean base value (also under the replacement cost archetype) | A replacement cost estimator (Verisk 360Value, Cotality) |
| `protection_class` | full address | clean base value; `not_found` when the rural archetype nulled it | Verisk LOCATION PPC |
| `kyc_score` | first name, last name, date of birth | clean base value; `not_found` when the profile archetype nulled it | An identity and adverse-media screen (LexisNexis Risk Solutions) |
| `p_f`, `slope_angle_deg`, `min_distance_to_neighbor_ft`, `vegetation_clearance`, `road_access` | full address | clean base value | Stand's own fire model and geospatial data |
| `roof_classification`, `siding_classification` | n/a | no provider; derive only | n/a |

"Full address" is `street_address`, `city`, `state` and `zip`. The prioritised hit list of next skills is in the README.

- A value an archetype set stays on the lead and is never replaced.
- The input check runs before the fixture lookup, so `blocked` outranks `not_found`.
- `blocked` adds the missing input to the ask plan and the lookup reruns after the reply. It does not raise a `data` blocker.
- `not_found` on `kyc_score` raises an `underwriter_review` item with name-search links; the underwriter closes it by entering a score with `resolve_fact` or declining with `decline_lead`. No model profiles a person.
- `unavailable` raises a `data` blocker.
- Fixture values are fixed per seed and do not depend on the system's plan.

### 9.5 Conflict validators

Code only. Each returns the fields involved and a neutral confirmation question, except the `kyc_score` range validator, whose case goes to the underwriter and has no question. A validator fires only on present values, except where its row names missing fields.

| Validator | Threshold source |
|---|---|
| `roof_replacement_year` later than the reference year | A date after the queue's morning cannot have happened |
| `roof_replacement_year` earlier than `year_built` | A roof cannot be replaced before the home exists |
| `effective_date` earlier than the reference date | A policy cannot start before the queue's morning |
| `electrical_panel_size_amps` below 60 | Assumption: 60 amps is the smallest residential service in common use |
| `number_of_residents` equal to 0 when `dwelling_use_type` is Primary, or `dwelling_type` is owner-occupied, or both of those fields are missing | A primary home has a resident; with no occupancy information the value still needs confirming |
| `acreage` equal to 0 | A dwelling sits on land |
| `months_unoccupied` of 1 or more when `dwelling_use_type` is Primary, or `dwelling_type` is owner-occupied, or both of those fields are missing | Agrees with I06; the generator injects this conflict whatever the occupancy fields hold |
| `dwelling_use_type` Primary with `is_rental` not "No" | A primary home is not let |
| `dwelling_type` owner-occupied with `dwelling_use_type` Secondary, Seasonal, Tenant or Mixed | The two fields describe one occupancy |
| `dwelling_use_type` Tenant or Mixed with `is_rental` "No" | A tenanted home is let (I53) |
| `water_heater_type` Tankless with `water_heater_age_years` or `water_heater_location` present | Tank-only fields on a tankless heater |
| `kyc_score` outside 1 to 10 | `unsupported`; goes to the underwriter |

The generator samples `year_built` and `roof_replacement_year` independently, so some generated leads trip the second validator. That is a real inconsistency in the data and is confirmed with the producer.

The same validators run on values extracted from replies.

### 9.6 Decision graphs

One YAML file per built detail page (seven files). Each declares `applies_when`. A small interpreter walks them. The five pages that are not built, and the Animals criterion of the overview (I46), are listed in `graphs/_not_encoded.yaml`, each with its `applies_when`.

**Node kinds**

| Kind | Meaning |
|---|---|
| `test` | Compares a field to values or bands. May cite an interpretation row. |
| `producer_question` | A fact with no registry field, from `catalogue.yaml`. |
| `underwriter_choice` | A judgment or an undefined term. Options are listed with no default; the option chosen is the decision, and a note is optional. |
| `outcome` | One or more typed effects. |

**Branch semantics, declared on every fan-out**

| Semantics | Meaning |
|---|---|
| `one_of` | Exactly one child applies (bands, enumerations). The loader checks completeness and non-overlap. |
| `all_of` | Every child is evaluated and effects combine. |
| `ladder` | Ordered fallbacks used in negotiation after a quote. Only the first rung is an effect; every later rung, a decline included, is recorded as an advisory for the underwriter alone and is not in the producer's packet. |

**Effects**

`decline`, `requirement` (text, deadline), `surcharge` (percent, rule id, optional deadline), `exclusion_or_endorsement`, `coverage_adjustment` (field, proposed value, optional deadline; the submitted value is kept), `advisory`, `obligation` (post-bind, with a trigger, never executed), `no_action`. A deadline on a surcharge or a coverage adjustment says how long the modification applies (I56).

Deadlines are a typed enum: `within_60_days`, `first_term`, `underwriting_period`, `within_30_days_of_bind`, `duration_of_non_occupancy`. They are never converted to one another.

**Usable facts.** A fact is usable when its effective observation is accepted and it is not part of an open conflict. Every source counts: submitted, fetched, derived, assumed, reply, underwriter. A derived fact is usable when its inputs are. A fact in an open conflict is evaluated as unknown until the conflict closes; its reported value is still shown and used in the confirmation question. A conflict closed under section 7.3 rule 6 is not opened again by the same validator on the same values.

**When each page applies**

| Page | `applies_when` |
|---|---|
| Profile | `kyc_score` above 5 (I02) |
| Occupancy | any I06 branch condition holds |
| Fire Simulation | `p_f` above 0.50 (I12) |
| Roof, Siding, Replacement Cost | always |
| Post & Pier | `foundation_type` is Piers, Stilts or Pilings (I23) |

The not-built pages apply as follows: Plumbing and Electrical always; Pools when `pool_type` is not "None"; Trusts when `residence_held_in_trust` is true; PC 9 & 10 when `protection_class` is "9" or "10"; Animals when `has_animals` is true. A lead a not-built page applies to carries a `not_evaluated` note naming the page; the page contributes no card, no decline and no question.

When `applies_when` rests on an unknown fact, the graph is undecided and contributes nothing: no card, no decline, no catalogue question. Triage fetches or asks for the missing fact. On seed 42 this keeps leads 001 and 005, whose `p_f` lookup is blocked, off the Fire Simulation page on the first pass.

**Node results.** Evaluation is three-valued. Each node returns `decided` (with effects), `undecided`, or `declines_on_every_branch`. "A decline" below means a decided node holding a `decline` effect or a node that is `declines_on_every_branch`.

| Node | Result |
|---|---|
| `test`, field usable | the selected child's result |
| `test`, field unknown | `declines_on_every_branch` when every child is a decline; otherwise `undecided`, naming the field |
| `producer_question`, unanswered | the same rule as a `test` on an unknown field |
| `underwriter_choice`, unanswered | `undecided`. Effects beneath it are possible, not committed. Choices nested beneath it are not shown until it is answered. |
| `all_of` | a decline when any child is a decline; otherwise `undecided` when any child is undecided, keeping the effects of decided children; otherwise `decided` with the union of effects |
| `ladder` | `decided` with the first rung's effect and an advisory listing the later rungs |
| `outcome` | `decided` with its effects |

**Collecting catalogue questions.** A catalogue question is collected when the branch selections leading to its node are settled by usable facts and answered choices. Unfinished sibling branches do not hold it back. Nothing is collected beneath an unknown `test` or an unanswered choice.

**Action plan.** Effects from all applicable graphs are collected, deduplicated by effect type and rule id, and kept with their rule trace. When one effect is both committed and possible, the interpreter keeps the committed copy. When any applicable graph's root is a decline, the plan is a proposed decline: no request goes out and the underwriter gets the decline notice draft to approve. A proposed decline shows no choice card and asks no catalogue question. If the underwriter rejects it, a ruling suppresses every rule id in the decline's trace, or in all its alternatives, for that lead. A suppressed decline outcome evaluates as decided with an advisory naming the overridden rule, which is for the underwriter and is left out of the packet, and the registry asks go out. Rejecting a notice that came from `decline_lead` withdraws that ruling; rejecting one that followed an underwriter choice reopens that choice when its option led straight to the decline, and suppresses the rule when the decline lay further down the graph.

`build_quote_packet` runs only when the plan holds no decline, no graph is undecided, no blocker is open and no ask remains. The workflow checks this before it calls the skill, and the skill refuses an input that breaks it.

**Rule traces.** Each graph node carries `board_path`, the list of board boxes it stands for, in order (for example `[07:LIVING, 07:D1]` for the node that declines on living-area support). A rule trace is the concatenation of `board_path` values from root to outcome. A decline reached as `declines_on_every_branch` carries `alternatives`: one trace per branch, each with the value it assumed. The Rule trace grader compares the trace, or the set of alternatives.

Acceptance cases:

- Post & Pier: a deck above 12 feet on a home built in 2000 or later declines whatever `post_pier_supports_living_area` is, with two alternative traces.
- Post & Pier: a deck height of 15 feet supplied by a reply declines; no packet is built.
- Lead 003: the Occupancy graph is undecided while the occupancy conflict is open.

**Order of precedence for the plan**

1. A decline at the root of any applicable graph makes the lead a proposed decline and suppresses all requests, confirmations included.
2. Otherwise, facts in an open conflict are unknown to the graphs and the confirmation joins the ask plan.
3. Otherwise the registry decides what is collected.
4. The playbook adds catalogue questions and document requests where the registry is silent.
5. Registry asks go out while an underwriter choice is open. Catalogue questions and document requests that sit under an unanswered choice are held until it is answered.
6. All open underwriter choices on a lead are shown as one card.

**Load-time checks.** Numeric bands complete and non-overlapping. Every outcome reachable. No outcome holds two effects of one type under one rule id. Every field exists in the registry or the catalogue. Every fan-out declares its semantics. Every row in section 9.7 is referenced by a node, marked `not_evaluated`, carries `applied_in` (naming the validator, derivation, resolution rule, rendering step, graph page or effect field that applies it).

### 9.7 Interpretation table

Each row is a ruling on something the board leaves open. Rows live in `interpretation.yaml` with id, source, ruling, kind and rationale. Kinds: **A** applied automatically and tagged `assumed`; **P** producer catalogue question; **U** underwriter choice; **N** not evaluated, shown as a non-blocking note.

These rulings are this submission's reading, not Stand's. Brett has reviewed every row; each carries `reviewed_by: Brett`.

**Boundary test.** Where the board states both sides of a line and leaves the exact value in neither, the exact value takes the stricter band. Where the board states one side only, the literal reading holds and there is no gap. Row I18 applies this test.

| Id | Page | Gap | Ruling | Kind |
|---|---|---|---|---|
| I01 | Profile | KYC scale undefined; example payload shows 82 | Scale is 1 to 10; other values are unsupported | A |
| I02 | Profile | KYC 5 or below | Page does not apply | A |
| I03 | Profile | "In the spotlight" versus "private" for KYC 6 to 7 | Both branches begin with Exclude Liability, so the quote carries the exclusion; the distinction is recorded as an advisory for negotiation. Traces use `02:SPOT`, `02:SPOT1` for KYC 6 to 7 (the generator's own note on these leads reads "in spotlight") and `02:HIGH`, `02:HIGH1` for KYC 8 to 10. | A |
| I04 | Profile | "Reputational damage to Stand" | Not evaluated by the system; the underwriter can decline at packet approval | N |
| I05 | Profile | "Deal killer" ladders | `ladder`: first rung in the packet, later rungs as an advisory | A |
| I06 | Occupancy | Which branch applies | Rentals when `is_rental` is not "No"; Vacant/Unoccupied when `months_unoccupied` is 1 or more; For Sale when `listed_for_sale` is true. Traces for the vacant or unoccupied branch use board box `03:UNOCC`, the box named after the registry field. | A |
| I07 | Occupancy | 60 days against a field in months | 1 month is under 60 days; 3 or more months is over 60 days; exactly 2 months is an underwriter choice | A, U |
| I08 | Occupancy | "Primary w/ Stand" | `has_primary_policy_with_stand` | A |
| I09 | Occupancy | Rental exceptions other than Tier 1 broker ("lead line", "well-managed in excess of $5m") | Underwriter choice between exception and decline | U |
| I10 | Occupancy | "Consider w/ modifications" | The listed modifications are effects on the quote | A |
| I11 | Occupancy | "Unrelated NIs" on the overview | Not evaluated | N |
| I12 | Fire Simulation | No field holds the simulation result | Fail when `p_f` is above 0.50; "Do Not Write" is never produced; at or below 0.50 the page does not apply. The threshold is this submission's invention and the first question for Stand. Generated values fall at or below 0.20 or at or above 0.55, so no generated lead distinguishes thresholds between them; hand cases at 0.21 and 0.54 record the dependence. | A |
| I13 | Fire Simulation | Decline versus legacy underwriting after a fail | Underwriter choice, shown with the legacy checklist values | U |
| I14 | Fire Simulation | Access wording against `road_access` options | Multiple Access Points continues; Limited / Dead-end / No Turnaround declines; Single Access Point and Unknown are an underwriter choice (`I14.road_access`). `road_access` drives the `04:INGRESS` branch; the separate `04:TURN` branch is not evaluated, since the registry's one value covers both. | A, U |
| I15 | Fire Simulation | Vegetation wording against `vegetation_clearance` | Too Close is Heavy; Adequate is Moderate/Light; Marginal and Unknown are an underwriter choice | A, U |
| I16 | Fire Simulation | "Steep" slope and "too close" neighbour distance have no thresholds | No number is invented; underwriter choice showing the value | U |
| I17 | Fire Simulation | Client willingness to mitigate | Producer catalogue question | P |
| I18 | Roof | Non-Class A at `p_f` exactly 0.50: the board's bands are "> .15 < .50" and "> .50" | The high band, by the boundary test: the board states both sides and leaves 0.50 in neither | A |
| I19 | Roof | "Or decline" beside a requirement | The requirement is the effect; decline remains the underwriter's option at packet approval | A |
| I20 | Roof | Roof age when the material is known; the Unknown Class branch | Class comes from the derivation map; roof age is handled by I52. The Unknown Class branch is not encoded. While `roof_material` is missing, a submitted roof class is used (section 9.3); with both missing the Roof graph is undecided on `roof_material`, which the registry asks for anyway. | A |
| I21 | Siding | Nine materials against two branches | Wood and Wood Shake / Shingle take the wood branch. Vinyl, Aluminum / Steel and Other (class C in the derivation map) take no action with an advisory on the quote. The rest take no action. | A |
| I22 | Siding | "Class A" on the siding page | Read as non-combustible siding | A |
| I23 | Post & Pier | When the page applies | `foundation_type` is Piers, Stilts or Pilings | A |
| I35 | Replacement Cost | "At RCE" tolerance | Within 10% either side. The tolerance is the row's parameter `tolerance: 0.10`, read by the graph. | A |
| I36 | Replacement Cost | "Reason to suspect fraud" | Not evaluated; underwriter's option at packet approval | N |
| I37 | Replacement Cost | Documentation above 150% | Document request in the message | P |
| I45 | All | "UWing period", "first term", "60 days" | Typed deadlines, not converted | A |
| I46 | Overview | Animals; other attractive nuisances | Not evaluated; non-blocking note on the lead | N |
| I47 | Pools, Post & Pier, Fire Simulation, Profile | Board notes and boxes calling for a map, listing or name-search check | Links for the underwriter; the registry's collection rule applies | A |
| I57 | Occupancy | Board note: "You can provide the quote without this information but you must follow up after" | The registry's always-required occupancy fields are requested before the quote | A |
| I52 | Roof | Composition shingles older than 20 years sit in neither Unknown Class list; the branch is unreachable once the material is known (I20) | Advisory on the quote for roofs whose `roof_material` is "Asphalt Fiberglass Composite" or "Architecture Shingles" with `roof_replacement_year` more than 20 years before the reference year and `p_f` above 0.15. A question for Stand. | A |
| I53 | Occupancy | `dwelling_use_type` Tenant or Mixed with `is_rental` "No" | Conflict validator (section 9.5); confirmed with the producer | A |
| I55 | Fire Simulation | "Determine preliminary mitigation plan to discuss with broker" | Advisory on the quote | A |
| I56 | Occupancy | Modifications apply "for duration of non-occupancy" | Deadline value `duration_of_non_occupancy` | A |

**Underwriter choices.** Labels and graphs take choice ids and option ids from this list, which `interpretation.yaml` holds under each U row.

| Choice id | Options |
|---|---|
| `I07.two_months` | `under_60_days`, `over_60_days` |
| `I09.rental_exception` | `exception`, `decline` |
| `I13.fire_fail` | `decline`, `legacy_underwriting` |
| `I14.road_access` | `multiple`, `limited` |
| `I15.vegetation` | `heavy`, `moderate_or_light` |
| `I16.slope` | `steep`, `gentle` |
| `I16.distance` | `adequate`, `too_close` |

**Fan-outs on Fire Simulation.** `04:LEGACY`, `04:MAP` and `04:ACCESS` are `all_of`. `04:VEG`, `04:INGRESS`, `04:MIND` and `04:SLOPE` are `one_of`.

**Rows that read more leniently than the alternative** (review these first): I03, I19, I20, I21. **Rows that are questions for Stand:** I12, I52.

## 10. Messages

### 10.1 Message classes

| Class | Recipient | Built from |
|---|---|---|
| Routine request | producer or applicant | field requests, follow-on questions and code-rendered confirmations of a conflicting value |
| Sensitive request | producer or applicant | any document request or catalogue question, or any draft a person has edited |
| Quote packet | producer or applicant | the action plan |
| Decline notice | producer or applicant | a fixed template, sent after the underwriter approves the decline |

A confirmation is rendered from a fixed neutral template and states no consequence, so it carries no more risk than a field request. The class a confirmation-only request takes is one value in `src/uwh/skills/vertical.py` (`confirmation_only_class`, which takes `routine_request` or `sensitive_request` and is set to `routine_request`), so an underwriter who wants to see confirmations first changes one value.

One open request per lead. A second request is allowed only after a reply. A quote packet or decline notice may follow an open request and closes it. After two rounds the lead goes to the underwriter.

### 10.2 Ask plan and rendering

The ask plan is a list of typed asks: `field_request`, `follow_on_question`, `catalogue_question`, `confirmation`, `document_request`. Each carries its field or catalogue id, its reason, and stored plain wording.

`render_message` produces the full text in code: a fixed opening, asks grouped by the registry's `section` in registry order, then a final group "Additional questions" for catalogue questions and confirmations, numbered. Each ask's id is recorded in the intent so graders can match the delivered body to the plan in both directions. Confirmations are worded neutrally and never state a consequence. No rendered message contains a decline reason, pricing or internal notes. An edited draft is not checked for them; the underwriter reads and approves every edited draft before it is sent.

**Conversational rewrite.** `polish_message` gives a request a conversational opening and closing. It applies to routine and sensitive requests only; a quote packet or decline notice is never rewritten. The model is shown the rendered request, the recipient kind and the round, and returns two pieces of text: an opening and a closing. Code builds the body as the opening, then the question block exactly as `render_message` produced it, then the closing. The model never returns the questions, so it cannot drop, add or change one.

Two checks run before the rewritten body is used, and both must pass:

1. **Code check.** Neither piece contains a question mark or a numbered line, and each is within its length cap (A.10).
2. **Model check.** A second call judges the opening and closing against the rendered request and answers whether they add a consequence, a decision, a price, a deadline or a request the rendered text does not contain. It returns pass or fail with the offending sentence.

When both pass, the rewritten body is the intent's body, the payload hash is taken over it, and the request keeps its class: a routine request still sends automatically. When either check fails, the skill abstains, or the skill is `failing` or `unavailable`, the rendered request is sent as it is and the event log records which check rejected the rewrite. An approval binds to the body the underwriter was shown, as for any draft.

### 10.3 Recipients

`contacts.yaml` is a labelled mock directory.

- `agent_portal` and `broker_email` leads go to the directory's address for that source (one address each).
- `direct_web` leads go to `owner_email` with applicant wording.
- With no address available, the lead gets an underwriter blocker "no contact route". The underwriter resolves it with `resolve_fact` on the internal fact key `q:contact_email`, which then is the recipient. A bind-only field is never requested to repair routing.

### 10.4 Replies

`POST /api/replies` (also behind a "paste a reply" box on the lead) takes lead id, intent id and body. Delivery is deduplicated by body hash per intent.

`read_reply` returns:

- a **classification**: `answers_all`, `answers_some`, `declines_to_answer`, `off_topic`;
- **candidate observations**: ask id, normalised value, and the quote: the reply text the value was read from, copied exactly. Values are extracted only for the asks in the open intent.

Then code:

1. finds each candidate's quote in the stored reply and records its offsets, taking the first occurrence when the quote occurs more than once; a candidate whose quote does not occur verbatim is dropped and the drop is recorded, because a quote that is not in the reply is an invented answer;
2. coerces values to the registry's types and option strings; a candidate for a field that was not asked, or whose value does not fit the field's type or options, is dropped and the drop is recorded, as for an unlocated quote;
3. runs the conflict validators;
4. applies the source-authority rules of section 7.3, for a reply classified `answers_all` or `answers_some` only;
5. closes the round when the classification is `answers_all` or `answers_some`; `off_topic` and `declines_to_answer` leave the round open and raise an underwriter review. The classification (Jev's when its confidence reaches the threshold, otherwise the model's) tells an on-topic reply from `off_topic` and `declines_to_answer`; for an on-topic reply, code decides `answers_all` or `answers_some` from the asks: `answers_all` when every ask still active after the reply's values is answered, a follow-on question those values make inactive counting as neither answered nor outstanding.

When `read_reply` abstains (A.10), the `reply_read` event records the abstention in place of a reading, the round stays open, and the reply goes to the underwriter unread as an underwriter review.

Reply text is untrusted. It is length-capped, passed to the model as data, and cannot approve an action. The model call runs outside any database transaction; then accepted facts, round closure and re-evaluation commit in one short transaction. A reply is refused unless its intent is `sent`, and a body already delivered for the intent is refused. With no key in live mode the reply is recorded unread and raises an underwriter review.

**Classification cascade.** With a Jev key (`TYPESAFE_API_KEY`), Jev answers the classification as a choice question. The interface computes confidence from the returned probabilities, and when it is below the per-question threshold (default 0.7) the language model answers instead; the confidence is the top outcome's probability, an on-topic reply (`answers_all` and `answers_some` together) being one outcome since code decides which, the model is still called for the candidates, and the `reply_read` event records which source answered and Jev's confidence. Jev's exchanges are recorded under `recordings/jev/`, keyed by the question version and the hash of the reply body and the options. Without a Jev key the language model answers every time, so the system works fully without Jev. When Jev gives no answer (an outage, or in replay no recording), a `skill_fallback_used` event records it, a miss also writes a `replay_miss` event, and the language model classifies; the reply is never refused for Jev. Each Jev call is a `model_called` event under Jev's model id with the usage it returns, and the `reply_read` summary says who classified and Jev's confidence. Brett and Stand's reviewers both run with a Jev key; the path without Jev is the fallback.

### 10.5 Quote packet and decline notice

The packet is built in code: coverages as submitted, coverage adjustments shown beside the submitted value, each surcharge on its own line, requirements with deadlines, exclusions and endorsements, advisories, obligations, and a note for each page that is not evaluated. A surcharge or coverage adjustment that carries a deadline shows it on its line. Money reads as dollars with thousands separators. No price, and no rule id: a rule that changes nothing adds nothing to the packet. An internal copy lists assumptions, the rule trace and the approver. Every packet and every decline notice waits for underwriter approval.

## 11. Underwriter surface

One page for an underwriter's desk, at least 1280px wide: the lead list on the left, the open conversation in the centre, a drill-down panel on the right when something is opened, and the demo controls pinned bottom right. `docs/build_logs/chat-surface.md` is its specification.

- **Lead list.** The one-sentence run summary heads it, with separate counts for quotes sent, follow-ups sent, declines approved, waiting on the underwriter, waiting on the producer, waiting on data, delivery unknown. "Follow-ups sent" counts every request sent to a producer, in any round; the brief calls the first request a follow-up. The four waiting counts count each lead once, by its primary next action: an underwriter review or question, a producer reply, a data blocker, or an unknown delivery. A "Queue" entry opens the queue conversation. Below it, one row per lead: its short name, address, status chip, primary next action, effective date and age against a two-business-day service level (Stand's distributor page promises estimates "inside two business days"; labelled as an assumed service level). Order: waiting on the underwriter, then waiting on the producer or data, then finished; within a group, earliest effective date first, then lead id.
- **Conversation.** A lead's conversation is its event log, oldest first, written by code: `event_summary` gives each event one sentence that names the fact, the result and what follows. Consecutive workflow events form one assistant message with a bullet per event. A message the system sent and a reply it read are bubbles. An item the underwriter acts on is a card at the event that opened it: a review (approve, edit, reject), a question (equal buttons, no default, required reason; all open choices on one lead share one card with the relevant values shown), a pending value, an unknown delivery. A resolved card stays in place as one read-only line. What the system did automatically is read from the same timeline; there is no separate notify item. Every bullet, bubble and card opens its evidence in the panel.
- **Queue conversation.** The run summary, then the open items of every lead as cards, and three example questions the server owns.
- **Chat.** Below the timeline sit the underwriter's typed messages and the assistant's answers, held in the browser's memory by run and conversation. The assistant is a second client of the command layer. One turn is at most eight steps of a forced tool call: a lookup, an answer or a proposal; the last step offers no lookup, so the turn answers from what it has, and a lookup repeated with the same arguments is not run again. The seven lookups (lead events, lead summary, messages, playbook path, current draft, queue summary, queue facts) read the views the page uses, and every result item carries a reference number of the turn. An answer cites numbers; the server keeps only those the turn's results showed and returns them resolved to an event, a fact, a message, a reply, a playbook page or a lead. A directive becomes a `propose_command` card on the lead it targets, which the underwriter applies or dismisses. Each message carries the last four exchanges of its conversation, which the prompt treats as data. `POST /api/chat` answers as a server-sent-events stream: a `step` per lookup, then exactly one closing `answer`, `proposal` or `error`. In replay the composer is disabled and the endpoint closes with "Questions need live mode" without a model call, except for an example question asked first in the queue conversation, which is answered from its recording.
- **Drill-down panel.** A citation chip or a card's "details" link opens it on a fact (value, source, the event that recorded it, the lead's other observations of the key), an event, a message, a playbook page (effect lines, board path ids, waits, not-evaluated notes) or the full lead (waiting on, facts, plan, messages, and the lead actions: paste a reply, resolve a fact, decline the lead).
- **Demo controls.** A separate card: "Load today's leads" starts the run, and asks first when a run exists; "Deliver the producers' replies" delivers every stored fixture reply for the run, so a default run exercises `read_reply` on several leads. It shows the mode ("live", "record" or "replay"), the seed and the run id.
- A confidence is shown only with its threshold: a reply Jev classified reads "Jev classified this reply (0.83, at or above the 0.70 threshold)", and a reply the model classified shows none.
- **Updates.** The page refetches after an action and every five seconds; a refetch does not touch a chat turn in flight.

## 12. Underwriter input

- Every approval, edit, rejection and ruling is captured with the actor, the artifact hash and a note. The structured choice (approve, reject, the option chosen) is the captured decision; the note is optional context, except for a decline: a decline keeps a required reason, asked once where the underwriter decides it: declining a lead, choosing decline at a choice, or approving a decline notice the playbook proposed; a notice that follows the underwriter's reasoned decline carries that reason and asks for none. The file carries it as the underwriter's decline. For a ruling the artifact hash is the lead's plan hash at that moment. Each becomes a **candidate** eval case; it joins the suite when reviewed.

## 13. Evals

### 13.1 Running

`docker compose --profile eval run --rm eval` runs the eval container. The runner imports the application in process with its own database path and points it at the `leadgen-eval` and `mailbox-eval` services, so an eval run never touches the interactive mailbox. A failed health or bootstrap check yields `invalid`, never a score. Every eval run, whether reference, fault or control, starts from an empty database file.

Faults are injected through one documented hook on the mailbox client (`FaultPlan`: fail after acceptance, return empty while a request is in flight). Send-safety faults run as separate fault runs on lead 008, never inside the reference run, so the reference run's labels hold. Injected faults are recorded on the run and are distinct from an invalid environment.

### 13.2 Expected results

- **Stand's answer key, as a hard grader.** The grader is record-directed: for every record in the generator's debug history it checks the system's ask plan. It regenerates the history by running the generator in process. Rules by record kind:
  - `missing_required`, and `missing_required_conditional` when the condition is active or unknown: the field appears as an ask or follow-on, unless the lead is a proposed decline or the field's resolution is `blocked`;
  - `archetype_null` on a producer-editable field: the same rule;
  - `archetype_null` on a system-owned field, `missing_bind_only`, `missing_system_owned` and `missing_derived`: never an ask;
  - `conflict`: a confirmation or an underwriter item; on a proposed decline the decline review satisfies it and is counted under the decline exemption;
  - `archetype_set`: no expectation.

  The grader has its own evaluation of the registry's six condition forms. For the two producer-editable conditional fields with no registry condition it encodes the section 9.2 table: `listed_for_sale` is always active, `is_gated_community` uses the three-valued pool condition, and `opening_protection` is never asked. Records decided by that table are counted separately, because that reading is this submission's, not Stand's (seed 42 has one, on lead 002).

  Two classes of disagreement are allowed and counted: a conditional field whose condition is inactive, and a field the perturbation pass nulled that a conflict injection set again. The residual outside those classes must be zero on seed 42. The run row also reports how many ask-expecting records were exempt because the lead was a proposed decline or the field was blocked; those two exemptions are decided by the system under test, so the counts are shown, and the seed-42 counts are pinned in the labels. The key is the one check whose expectations Stand wrote.
- **Per-page cases.** One table of hand-written cases per page: one row per outcome node, plus every boundary named in section 9.7.
- **Seed-42 labels.** Expected first-pass state and message asks for the ten leads. The runner grades these at the settle point, before any scripted underwriter action. It then plays the label's `underwriter_actions` and grades the expectations held under the label's `after_actions` key with the same graders (Coverage, One open request, Asks, Forbidden asks, Rule trace, Packet fidelity). Each score records the phase, `first_pass` or `after_actions`, in which a failure occurred.
- **Reply fixtures.** Full, partial, contradicting, and instruction-bearing, each with expected facts and state. Producer answers are hand-written. Reply bodies live in `fixtures/replies/` at the repository root and ship in the app image for the fixture-reply control; their expected results live in `evals/labels/` and do not.

Labels are written from the playbook transcriptions, the registry and the data files under `src/uwh/rules/data/` by an agent that does not read the Python under `src/uwh/rules/`. Brett signs the ten lead labels. `evals/` and every `cases/` folder stay out of the app image.

Labels and graphs share one id scheme: board boxes are named by page number and Mermaid node id from `docs/playbook/` (for example `07:LIVING`, `07:D1`), and traces are built as section 9.6 describes.

**Case coverage.** The per-page cases are a table per page under `evaluate_playbook/cases/`: one row per outcome node plus every boundary named in section 9.7. `evals/labels/seed42/exemptions.yaml` pins the answer-key exemption counts for seed 42 (26 records exempt on lead 000's proposed decline, 0 exempt as blocked); the grader fails when a run's counts differ.

**Held-back reply cases.** Three further hand-written replies, under `fixtures/replies/held/`, are kept from the `read_reply` implementer until the eval run. The improvement cycle is run on a case that fails that run. If none fails, the results log says so and no cycle is staged.

### 13.3 Graders

Nine graders, plain functions over the mailbox, event log and fact ledger. The Chat row is the check of milestone 4's chat cases and is not one of the nine.

| Grader | Checks |
|---|---|
| Coverage | Every lead has a primary next action or is terminal; no lead is skipped |
| One open request | At most one unanswered request per lead, and no duplicate as section 7.5 defines it |
| Asks, both directions | Delivered asks equal the expected asks: none missing, none extra |
| Forbidden asks | No ask for a system-owned, bind-only, or inactive conditional field |
| Rule trace | Every decline and every requirement has a rule trace; the path matches the expected path |
| Packet fidelity | Every effect in the plan appears in the delivered packet |
| Send safety | Crash after mailbox acceptance, and query-empty-while-in-flight, each yield no second message. A fault run with no `fault_injected` event fails. |
| Stand's key | The residual described in section 13.2 is zero |
| Reply reading | Extraction and classification against fixtures. The eval runs in replay, where the repeat check is reported as not applicable. |
| Chat | A question causes zero commands; a refused directive stays refused when reworded |

No `/debug` path under `src/` is a static check in `scripts/check_discipline.py`, not a grader.

**Critical errors** (any one fails the run): duplicate send, unauthorised send, a requirement missing from a delivered packet, a reply approving an action.


Tokens and wall time per lead are reported as measurements on every run row. They are not a grader.

### 13.4 Controls

A reference run passes everything. Each broken variant must be failed by its named grader:

| Variant | Failed by |
|---|---|
| Do nothing | Coverage |
| Email every lead with every missing field | Forbidden asks; Asks |
| Send twice | Send safety; critical errors |

### 13.5 Results log and loop

`evals/results.jsonl`, committed and append-only. A `run` row per run: run id, commit, evaluator hash, case-set id, skill digests, scores, critical errors, tokens and cost, hypothesis, and the suite, control, mode and status (`scored`, or `invalid` with its reason and no scores). A `decision` row, written by a person after reading the run, names the run id and says keep or discard with a reason. The submission includes one real cycle on reply reading: a failing held-back reply case, the diagnosis, one prompt change, the rerun, the keep decision.

## 14. Dependencies and packaging

| Service | Profile | Built from | Host port | Storage |
|---|---|---|---|---|
| `leadgen` | default | `sim-harness/leadgen/Dockerfile`, context `./sim-harness` | 8081 | named volume |
| `mailbox` | default | `sim-harness/mailbox/Dockerfile`, context `./sim-harness` | 8025 | named volume |
| `app` | default | `Dockerfile` (multi-stage: frontend build, then Python) | 8000 | named volume |
| `leadgen-eval`, `mailbox-eval` | `eval` | same Dockerfiles | none | separate named volumes |
| `eval` | `eval` | the app image plus `evals/`, every `src/uwh/skills/*/cases/` folder, and `sim-harness/leadgen` with `sim-harness/shared` (for regenerating Stand's key in process) | none | writes `evals/results.jsonl` through a bind mount; `recordings/` mounted read-only, and read-write only when `RECORDINGS_ACCESS=rw` is set for a record run |

- The app stage copies `src/` selectively and leaves out every `cases/` folder. It copies `docs/brief/field_registry.json` to `/app/registry/field_registry.json`; the setting `UWH_REGISTRY` names that path. It copies `fixtures/replies/` to `/app/fixtures/replies` (`UWH_FIXTURE_REPLIES`); `recordings/` is mounted at `/app/recordings` (`UWH_RECORDINGS`). The commit hash reaches the images as the build argument `GIT_COMMIT`, since `.git` is outside the build context. The make targets set it from `git rev-parse HEAD`. With plain `docker compose up` it is unset and the images carry `unknown`, which is fine for running the app; eval runs go through `make eval`, and a run row with commit `unknown` fails its check. A root `.dockerignore` keeps `.env`, `.git`, `.venv`, `web/node_modules` and `web/dist` out of the build context.
- Stand's code and Dockerfiles are unmodified. Stand's own `docker-compose.yml` stays in place, unused; ours keeps Stand's documented host ports.
- Database paths are set through `LEADGEN_DB` and `MAILBOX_DB`. `DEBUG` passes through as `${DEBUG:-false}`, so a reviewer can switch the answer key on for their own use; the application client has no debug method either way.
- Inside the network the app calls `http://leadgen:8080` and `http://mailbox:8080`.
- "Load today's leads" recreates every app table, resets the interactive mailbox and posts the queue for `SEED` (default 42), count 10. A start is refused while a run is still processing or a message is being sent. Every commit and dispatch checks that its run id is the current one, so work left over from a replaced run writes nothing.
- Replay mode uses its own app database and a `replay` run id; it writes to the interactive mailbox after a reset.
- `.env` must exist: the README's first step is `cp .env.example .env`. It is passed into the app and eval services explicitly, along with `LEADGEN_URL` and `MAILBOX_URL` (defaults `http://leadgen:8080` and `http://mailbox:8080`; the eval overrides them). `.env.example` documents `MODEL_API_KEY` (a DeepSeek key), `MODEL_BASE_URL` (default `https://api.deepseek.com/anthropic`), `MODEL_ID` (default `deepseek-flash`), `TYPESAFE_API_KEY` (optional), `RUN_MODE`, `SEED`, `DEBUG`.
- `.gitattributes` sets `eol=lf`. The frontend builds inside the container. Images build for linux/amd64 and linux/arm64.
- Stage 13 runs the compose file on macOS (arm64), on an amd64 Linux host, and on Windows with WSL2, and records each result in the README. A platform that was not run is stated as not run.
- Requires Docker Compose 2.20 or later.
- Stage 1 checks the forced tool call against DeepSeek's documentation and with a live call, and pins the SDK version in the lockfile.

## 15. Open issues

1. Stand's compose behaviour under our service definitions is verified by `tools/fresh_clone.py`.
2. Jev's access and live output shape are unverified until a key exists.
3. Interpretation rows are our reading. Rows marked U interrupt the underwriter on every matching lead until a ruling turns them into A rows.
4. The generator draws six states; Stand writes in two. No eligibility rule by state is invented.

## 16. Resolved issues

Dispositions of `docs/build_logs/critique.md` findings.

| Finding | Disposition | Where |
|---|---|---|
| C01 no cut line | Accepted. The cut line is stated once and one scope is built. Jev is not cut. | 4.1 |
| C02 missing contracts | Accepted. | Appendix A |
| C03 underwriter question versus producer request | Accepted. | 9.6 rules 5 and 6; section 5 rows 003, 006 |
| C04 eval grades its own reading | Accepted. Stand's key is a hard grader with enumerated allowed disagreements. | 13.2, 13.3 |
| C05 zero model calls on the first pass | Accepted. Fixture-reply control and the harness statement. | 8, 11 |
| C06 provider fixture limits | Accepted. Fingerprint, `unavailable` on a mismatch, seed from the environment, plain statement. | 9.4 |
| C07 eligibility decisions under the A tag | Accepted for I07 and I21. I12 keeps 0.50, is marked as invented and as a question for Stand, with hand cases. Lenient rows are listed for review. | 9.7 |
| C09 board gaps with no row | Accepted. | 9.7 I52, I53, I55, I56, I57 |
| C10 validators fitted to the generator | Accepted. Sources stated; occupancy threshold agrees with I06; roof-before-build and two validators the generator does not inject are added. | 9.5 |
| C11 path exploration | Accepted. Three-valued evaluation. | 9.6 |
| C12 skill status | Accepted. | 8, A.4 |
| C13 over-escalation | Accepted. Code-rendered confirmations are routine; one card per lead; a headline escalation rate. Three seed-42 leads need the underwriter on the first pass (000, 003, 006). | 10.1, 11, 13.3 |
| C14 eval topology | Accepted. | 13.1, 14 |
| C15 packaging | Accepted. | 14 |
| C16 reply confirming a conflict | Accepted. | 7.3 rule 6 |
| C17 roof age unreachable | Accepted as an advisory row and a question for Stand. | 9.7 I52 |
| C18 SDK claims, model id | Accepted. | 14 |
| C19 cut Jev | Declined by Brett's decision. Jev is built and is not cut. Brett and Stand's reviewers run with a Jev key; the language model alone is the fallback. | 4.1, 10.4 |
| C20 small inaccuracies | Accepted. | 1, 2.2, 14 |
| C21 service-level source | Accepted. Labelled as an assumed service level with its source. | 11 |
| C23 answer-key grader | Accepted. | 13.3 |
| C24 contacts keyed per lead | Accepted. | 10.3 |
| C25 crash recovery | Accepted. | 7.5 step 5 |
| C26 hit list and real providers | Accepted. | 9.4; README |
| C27 three-state objective | Accepted. | 1 |
| C28 values a builder would guess | Accepted. | Appendix A |

## 17. Alternatives considered

| Alternative | Why not |
|---|---|
| An agent framework driving a model through tools | The process is written down as rules; "one message" and approval binding are easier to guarantee in a fixed workflow |
| One pipeline application with skills as a README list | Reads as one agent; Stand asked for a harness |
| A learned or typed decision model on the decision path | The playbook is threshold bands over known fields; a model adds a failure mode and removes the rule trace |
| A second encoding of the trees as an oracle | Shares the first encoding's reading; per-outcome hand cases give outcome truth instead |
| A seeded reply simulator | Test-data infrastructure, named out of scope by the harness README |
| Including Stand's compose file | Hard-coded ports and one shared mailbox; an eval run would wipe the demo |
| Model-written questions | The questions come from the plan; free text adds a content risk and no information |
| A graph database per lead | 73 fixed fields with fixed relations; two tables give the same "why" trace |
| Inspect AI as the runner | Most graders are checks on stored state; named as the next step when judgment points multiply |
| Live third-party data | Addresses are invented; a live call adds risk and no information |

## Appendix A. Contracts

This appendix fixes names, tables, routes, commands and semantics. It does not spell out every field of every event payload, route response and skill input or output; the Pydantic models and the OpenAPI file hold those shapes.

### A.1 Tables

```sql
leads(lead_id TEXT PRIMARY KEY, run_id TEXT, source TEXT, received_at TEXT,
      status TEXT, revision INTEGER, plan_json TEXT, plan_hash TEXT)
events(id INTEGER PRIMARY KEY, run_id TEXT, mode TEXT, lead_id TEXT, type TEXT, payload_json TEXT,
       actor TEXT, ruleset_hash TEXT, prompt_versions_json TEXT, model_id TEXT,
       request_id TEXT, real_ts TEXT, sim_ts TEXT)
observations(id INTEGER PRIMARY KEY, lead_id TEXT, key TEXT, value_json TEXT, source TEXT,
             evidence_json TEXT, status TEXT, event_id INTEGER)
effective_facts(lead_id TEXT, key TEXT, observation_id INTEGER, confirmed INTEGER,
                PRIMARY KEY (lead_id, key))
blockers(id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT, kind TEXT, owner TEXT, detail_json TEXT,
         opened_event_id INTEGER, closed_event_id INTEGER)
intents(id TEXT PRIMARY KEY, run_id TEXT, lead_id TEXT, round INTEGER, kind TEXT,
        recipient TEXT, subject TEXT, body TEXT, ask_ids_json TEXT, payload_hash TEXT,
        state TEXT, mailbox_id INTEGER, lead_revision INTEGER)
        -- lead_revision: the lead's revision when the draft was built; a draft at an older revision is never sent
        -- state: draft | dispatching | sent | unknown | closed_unsent
        -- kind: routine_request | sensitive_request | quote_packet | decline_notice
approvals(id INTEGER PRIMARY KEY, lead_id TEXT, item_kind TEXT, intent_id TEXT,
          lead_revision INTEGER, plan_hash TEXT, ruleset_hash TEXT, recipient TEXT,
          payload_hash TEXT, actor TEXT, decision TEXT, reason TEXT, event_id INTEGER)
          -- item_kind: draft | observation | delivery_unknown | no_contact_route | review; decision: approved | rejected
          -- edits and rulings are recorded on their events, not here
runs(run_id TEXT PRIMARY KEY, seed INTEGER, mode TEXT, started_at TEXT, status TEXT)
          -- status: processing | settled
proposals(id INTEGER PRIMARY KEY, payload_json TEXT, state TEXT, actor TEXT, event_id INTEGER)
          -- each row is a proposed command; state: open | applied | dismissed
```

`key` is a registry field name or a catalogue id prefixed `q:`. Blocker `owner` is `underwriter`, `producer` or `data_team`. The store enforces every value set this section and section 7 name: `leads.status`, `blockers.kind`, `blockers.owner`, `intents.kind`, `intents.state`, `approvals.item_kind`, `approvals.decision`, `observations.source`, `observations.status`, `runs.status`, `proposals.state` and the run mode. `runs` holds one row, the current run. A start recreates the tables with `blockers.id` continuing above the last id of the run it replaces, so an item id never repeats across runs.

### A.2 Event types

`run_started`, `replay_miss`, `draft_edited`, `proposal_created`, `lead_received`, `fact_observed`, `fact_selected`, `conflict_opened`, `conflict_closed`, `triage_completed`, `provider_called`, `plan_built`, `blocker_opened`, `blocker_closed`, `intent_created`, `message_sent`, `delivery_unknown`, `reply_received`, `reply_read`, `approval_recorded`, `ruling_recorded`, `command_refused`, `skill_fallback_used`, `model_called`, `fault_injected`.

Each payload is a Pydantic model named after the type. Graders import those models. `draft_edited` carries the intent's kind after the edit (section 7.5). `provider_called` carries the field looked up and the section 9.4 provider result as one nested object, the same model the providers return. No event records a status change, the move to `dispatching` or the closing of a round. A lead's status is held in `leads.status`. The move to `dispatching` is held in `intents.state`. Round state is held in the reply-wait blocker: a round is open while that `producer_reply` blocker is open, and it closes with `blocker_closed`.

### A.3 Status transitions

`received → triaged → in_progress → quote_sent | declined`. `received` and `triaged` also move to `declined`, so `decline_lead` ends any lead that is not terminal. `in_progress` re-enters itself on re-evaluation. `quote_sent` and `declined` are terminal; a reply arriving after either is recorded and raises an underwriter review without changing the status.

### A.4 Hashes and digests

All hashes are SHA-256 over canonical JSON (sorted keys, UTF-8, no insignificant whitespace).

- **Lead revision:** an integer, incremented whenever an effective fact changes or a ruling is recorded.
- **Plan hash:** the action plan.
- **Ruleset hash:** every file under `src/uwh/rules/data/`, in path order.
- **Payload hash:** `{recipient, subject, body}`.
- **Skill digest:** every source file in the skill's folder except `cases/`, plus every Python source file under `src/uwh/` outside the skill folders, including the modules directly under `skills/` (one shared hash, so a change to the rules core, providers or runtime marks every skill `untested`), plus the hash of the image's `src/uwh/rules/data/`, plus the model id for model skills. Compiled files (`__pycache__`, `*.pyc`), hidden files and directories (a path part starting with `.`), `*~` and `*.swp` are never hashed, in the skill digest or in the ruleset hash, so a file an editor or an operating system leaves behind cannot change either. The results row records the case-set id beside the digest.

### A.5 Routes (app on port 8000)

| Method and path | Purpose |
|---|---|
| `GET /api/run` | Run id, mode, seed, simulated time, summary counts |
| `POST /api/run/start` | Reset and ingest the queue. Returns at once with the run id; with `?wait=true` it returns when the run has settled, meaning no lead has a runnable workflow step. `GET /api/run` reports the same condition as `first_pass_complete`. A settled run has every lead terminal or blocked. The UI uses the waited form. The response reports the run this request started, or answers 409 when a later start replaced it. |
| `GET /api/leads` | Queue rows in display order |
| `GET /api/leads/{id}` | Lead detail: facts, plan, rule trace, notes; blockers with their `item_id`, and `intent_id` when the blocker is a draft review; drafts with `intent_id` and `payload_hash`; open choices with their `choice_id` |
| `GET /api/leads/{id}/events` | Event log for a lead |
| `GET /api/items` | Open review and question items across leads |
| `POST /api/commands` | Submit a typed command `{type, payload}`; the response is accepted or refused with a reason |
| `POST /api/replies` | Deliver a reply `{lead_id, intent_id, body}`. Returns after the reply has been read and the lead re-evaluated. Accepted only for an intent in state `sent`. |
| `POST /api/replies/fixtures` | Deliver every stored fixture reply for the run. Returns after all are processed. |
| `GET /api/proposals` | Proposal cards stored by `propose_command` |
| `POST /api/chat` | One chat turn, answered as a server-sent-events stream: a `step` per lookup, then one closing `answer`, `proposal` or `error` |

### A.6 Graph file format

```yaml
# src/uwh/rules/data/graphs/roof.yaml
id: roof
page: docs/playbook/05-roof-class/flowchart.md
applies_when: {always: true}
root: roof_class
nodes:
  roof_class:
    kind: test
    field: roof_classification
    board_path: ["05:ROOT"]
    cases:
      - {when: {equals: Class A}, then: okay_class_a}
      - {when: {in: [Class B, Class C]}, then: non_class_a_band}
  non_class_a_band:
    kind: test
    field: p_f
    interpretation: I18
    board_path: ["05:NCA"]
    cases:
      - {when: {lte: 0.15}, then: okay_low}
      - {when: {gt: 0.15, lt: 0.50}, then: confirm_first_term}
      - {when: {gte: 0.50}, then: confirm_60_days}
  okay_class_a: {kind: outcome, board_path: ["05:CA", "05:OK_A"], effects: [{type: no_action, rule: RF-1}]}
  confirm_first_term:
    kind: outcome
    board_path: ["05:N_MID", "05:N_MID_R"]
    effects:
      - {type: requirement, rule: RF-3, text: "Confirmation of a Class A roof or its replacement", deadline: first_term}
```

- `applies_when` may be `{any: [...]}`: true when any member is true, otherwise unknown when any member is unknown, otherwise false.
- Conditions use `equals`, `in`, `lt`, `lte`, `gt`, `gte`. A bound may be a literal or `{one_minus: I35.tolerance}` or `{one_plus: I35.tolerance}`, which are one minus and one plus a parameter of the named interpretation row.
- A node is a `test` (a field and `cases`, each a condition and the node it leads to; the cases are `one_of`), a `producer_question` (a `test` on the catalogue answer `q:<id>`), an `underwriter_choice` (`choice`, `prompt`, `show` and `options`, each option leading to a node), an `all_of` (its `children`), a `ladder` (its `rungs`) or an `outcome` (its effects). A node may carry `interpretation: I18`. The load check refuses a graph that leads to a missing node, has a node no path reaches, names a choice or options the interpretation table does not, or has an outcome with two effects of one type for one rule.
- A `test` whose cases are numeric bands must cover every number once: the graph file is refused at load when the bands leave a gap or overlap. A test on discrete values is not checked.
- A `test` may name a **derived input** in place of a registry field. `derivations.yaml` declares the two that exist: `coverage_to_rce_ratio` (`coverage_a / replacement_cost`) and `roof_age_years` (the reference year minus `roof_replacement_year`). A derived input is unknown when any input is unknown or the divisor is zero. No general expression language exists.
- Interpretation rows may carry `params` (a map of named numbers). The Replacement Cost graph bands `coverage_to_rce_ratio` at `1 - I35.tolerance`, `1 + I35.tolerance` and 1.5.
- A ratio over 1.5 takes the requirement RC-4: documentation of the Coverage A amount, with the quote at the calculated replacement cost without it. The catalogue's document request `rce_documentation` (I37) is not asked.

### A.7 Catalogue of producer questions

`catalogue.yaml` holds id, wording, answer type and the interpretation row for each: `willing_to_mitigate` and `rce_documentation` (document request).

`wording.yaml` holds one plain-language question per producer-editable registry field, one conditional preamble per `requiredWhen` form that a follow-on question can take, and one neutral confirmation template per validator whose confirmation goes to a producer, and one combined template for the two validators that both name `dwelling_use_type` (owner-occupied with another use, and Tenant or Mixed use with `is_rental` "No"): when both fire, the combined template replaces the two, so `dwelling_use_type` is asked once. The `protection_class in (9, 10)` form has no preamble, since its dependents are `blocked` and never follow-ons (section 9.2); `is_gated_community` is asked with no preamble; and the `kyc_score` range validator has no template, since that case goes to the underwriter (section 9.5). Each validator has an id and lists the fields it covers. A test asserts every producer-editable field has an entry.

### A.8 Message text

- From `uw@stand.com` (the address in the harness README's example).
- Subjects: "Information needed for your quote: <address or lead id>", "Your quote: <address or lead id>", "Regarding your submission: <address or lead id>".
- Fixed opening for requests: "Thank you for your submission. To complete the quote we need the items below. One reply covering all of them is ideal."
- Asks are grouped by the registry's section and ordered by registry order within a section.

### A.9 `read_reply` output

```python
class Candidate(BaseModel):
    ask_id: str            # an ask id from the open intent: field name, catalogue id or validator id
    field: str             # the registry field or q: id the value is for; for a confirmation,
                           # one of the fields its question reports
    value: str | int | float | bool
    quote: str             # the reply text the value was read from, copied exactly; not empty

class ReplyReading(BaseModel):
    classification: Literal["answers_all", "answers_some", "declines_to_answer", "off_topic"]
    candidates: list[Candidate]

class LocatedCandidate(Candidate):
    span_start: int        # computed by code, never by the model
    span_end: int          # body[span_start:span_end] == quote
```

`ReplyReading` is what the model returns: its JSON schema is the input schema of the forced tool, and it holds no offsets. Code then locates each candidate's `quote` in the reply body:

- The quote must occur verbatim in the body. A candidate whose quote is not found is dropped and yields no observation; the drop is recorded on the `reply_read` event with the candidate as the model returned it.
- A candidate whose field was not asked, or whose value does not fit the field's type or options, is dropped the same way and recorded in the same list.
- When the quote occurs more than once, the first occurrence is taken.
- A found candidate becomes a `LocatedCandidate`. The stored output of `read_reply` is the classification with the located candidates, so everything downstream that shows a span reads `span_start` and `span_end` from it.

Reply bodies are capped at 8,000 characters. The model id comes from `MODEL_ID`. The prompt lives in `src/uwh/skills/read_reply/prompt.md`.

### A.10 Fixed values

- Lead concurrency: 4.
- Skill pass threshold: 1.0 unless a manifest states another value with its reason.
- `read_reply` sends a forced tool choice with `thinking` disabled, and `temperature` 0. The Anthropic SDK from 1.0 has no `temperature` argument, so the value goes in the call's `extra_body`. A tool input that fails validation repeats the call once; a second failure, or a `refusal` stop reason, maps to the skill's typed abstention. The abstention's reason is one of two codes, `invalid_tool_input` and `refusal`, and nothing else. Stage 1 confirms with DeepSeek's documentation and a live call that `MODEL_ID` accepts the forced tool choice and the temperature; whether `temperature` 0 gives agreeing repeats is measured by the three-repeat check of the Reply reading grader.
- `polish_message` makes its two calls the way `read_reply` does: a forced tool choice with `thinking` disabled, `temperature` 0 in `extra_body`, one repeat on an invalid tool input, then the typed abstention. Length caps: opening 600 characters, closing 300.
- Rounds before the lead goes to the underwriter: 2.
- Jev confidence threshold: 0.7 per question, in the skill manifest.
- Reply-reading repeats in evals: 3.

### A.11 Commands

`POST /api/commands` takes `{type, payload}` and returns `{accepted: bool, event_id: int | null, reason: str | null}`.

| Type | Payload |
|---|---|
| `approve` | `{item_id, artifact_hash, reason}`; `artifact_hash` is the payload hash shown with the draft. It is required when the item is a draft and omitted otherwise |
| `reject` | `{item_id, reason}`; `reason` required |
| `edit_draft` | `{intent_id, subject, body, reason}` |
| `record_ruling` | `{lead_id, choice_id, option, reason}` |
| `resolve_fact` | `{lead_id, key, value, reason}`; records an underwriter observation |
| `decline_lead` | `{lead_id, reason}`; makes the plan a proposed decline with the reason as its trace and drafts the decline notice |
| `deliver_reply` | `{lead_id, intent_id, body}` |
| `start_run` | `{seed}` |
| `propose_command` | `{type, payload, rationale}`; stores a proposal card, executes nothing; the underwriter applies it by submitting the proposed command. The proposed command is never `approve`, `reject` or `propose_command` |

`item_id` is the id of an open blocker (`blockers.id`). What `approve` and `reject` do depends on the item:

| Item | `approve` | `reject` |
|---|---|---|
| Draft request | dispatches it | returns it to draft for editing, with the reason |
| Draft quote packet | dispatches it | returns it to draft; the underwriter declines with `decline_lead` |
| Draft decline notice | dispatches it; the lead becomes `declined` | records a ruling that suppresses the declining rule for this lead; registry asks go out |
| Pending observation | makes it the effective fact | marks it rejected; the existing value stays |
| `delivery_unknown` | re-runs the mailbox check | closes the intent unsent; a fresh draft waits for approval |
| No contact route | n/a; resolved with `resolve_fact` on `q:contact_email` | n/a |
| A review raised by an event (a late or unread reply, an off-topic or declining reply) | acknowledges it with a reason and closes it; when a reply raised it, the round closes too | refused; the underwriter acts through `resolve_fact`, `record_ruling` or `decline_lead` |
| A review whose cause persists (the round limit, a missing or unsupported identity score) | refused | refused. It closes when the cause is removed: `resolve_fact` supplies the fact, or `decline_lead` ends the lead. |

Every item above is an `underwriter_review` blocker, except `delivery_unknown` (its own kind) and an open choice (`underwriter_question`). Each blocker in the lead detail response carries its kind and, in its `detail`, its item kind (the `approvals.item_kind` values in A.1) and, for a review, its cause; each open choice carries its option ids. Every accepted command re-evaluates its lead in the same transaction. The re-evaluation builds drafts and dispatches nothing; a draft whose class runs at `auto` is dispatched after the command commits (section 7.5). When a step fails during the re-evaluation, the whole re-evaluation rolls back to its savepoint, so no part of the pass is kept, and the step-failure `data` blocker opens (section 7.1); the command's own writes commit, so an underwriter can always correct a fact.

Workflow-only classes (`fetch_data` and the send classes) are submitted in process and are not accepted over HTTP.
