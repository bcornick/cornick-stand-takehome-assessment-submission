# Underwriting triage on a skill-and-eval harness

Brett Cornick's submission for the Stand Insurance take-home (`docs/brief/agentic_uw_takehome.md`). The app takes the ten seed-42 leads that Stand's generator posts and drives each to a sent quote packet, one sent request to the producer, or a wait on the underwriter with a stated reason. Every send of a quote packet or decline notice waits for an underwriter's approval. `docs/architecture.md` is the design authority; `docs/plan.md` is the scope.

## Run it

Prerequisites: Docker with Compose 2.20 or later, and `uv`. The frontend builds inside the image. `make check` also needs `jq`, Node 22 and pnpm (`corepack enable`).

```
cp .env.example .env
make up
```

Open `http://localhost:8000`. The first build takes a few minutes. Stand's leadgen answers on host port 8081 and the mock mailbox on 8025; `APP_PORT`, `LEADGEN_PORT` and `MAILBOX_PORT` move the three.

To see the demo:

1. Click **Start morning run**. The app posts the ten leads and settles them.
2. Open lead 008 in the queue. The detail pane shows its facts with their sources, the playbook path, and the request the system sent.
3. Click **Deliver fixture replies**. Every stored producer reply is delivered and read; lead 008's reply is read and its lead becomes a quote packet draft.
4. Back on lead 008, **Approve** the packet. The mailbox then holds one request and one packet for it.

Leads 000, 003 and 006 need the underwriter on the first pass: 000 is a proposed decline that waits for approval, and 003 and 006 each show one question card.

### Run modes

`RUN_MODE` in `.env` picks the mode, and the page always shows it.

- `replay` (the default): every model and Jev exchange is served from `recordings/`. No key is needed and no model host is called. A request with no recording fails closed with a visible error; a Jev miss falls back to the language model.
- `live`: calls DeepSeek with `MODEL_API_KEY`. Nothing reads or writes a recording.
- `record`: as live, and each exchange is written to `recordings/`. Also set `RECORDINGS_ACCESS=rw`, because the folder is mounted read-only otherwise.

`MODEL_API_KEY` is a DeepSeek key; `MODEL_BASE_URL` and `MODEL_ID` default to the Anthropic-format endpoint and `deepseek-flash`. `TYPESAFE_API_KEY` switches on Jev, which classifies a reply first; with it empty the language model classifies every reply, and the system works fully without Jev. Without `MODEL_API_KEY`, live mode records a delivered reply unread and raises an underwriter review.

### Commands

```
make check        # lint, types, discipline checks, fast tests, frontend checks
make test-slow    # slow and integration tests; needs the containers running
make eval         # one eval suite in the eval containers, in replay
uv run python tools/fresh_clone.py
```

`make eval` runs the seed-42 suite by default. Pass `ARGS="--suite replies"`, `ARGS="--suite chat"` or `ARGS="--control do_nothing"` for the others; `--jev` classifies with Jev from `recordings/jev` and needs `TYPESAFE_API_KEY`. The target refuses a working tree with uncommitted changes, because each result row names its commit, and appends a row to `evals/results.jsonl`.

`tools/fresh_clone.py` clones HEAD into a temporary directory, copies `.env.example` with no keys, brings the stack up in replay under its own compose project and ports, runs the first pass and the fixture replies, then removes everything. It clones committed files only. Platforms: the rehearsal has been run on macOS arm64. Linux amd64 and Windows with WSL2: not run. Images are defined for amd64 and arm64.

## Architecture

```
Stand's leadgen --> run start --> workflow (per lead, bounded pool) --> skills --> drafts
Stand's mailbox <-- send path <-- command layer <-- underwriter UI, chat, workflow, reply endpoint
                                  event log + fact ledger (SQLite) under all of it
```

**Lead workflow.** "Start morning run" posts the queue from the leadgen service. Each lead runs through a fixed list of steps: field triage against Stand's registry, data resolution (derive, fetch from the stand-in providers, assume), playbook evaluation over the seven built pages, the ask plan, and the rendered request. A lead holds a status and a set of open blockers (producer reply, underwriter review, underwriter question, data, delivery unknown); its next action is the highest-priority blocker. A producer's reply is read, its values enter the ledger, and the lead re-evaluates from the top until it reaches a packet draft or a stated wait. A routine request goes out on its own; a sensitive request, the packet and the decline notice go out only on approval.

**Command layer and actors.** Every state change is a typed command: nothing else writes. The actors are the workflow, the underwriter, the assistant (chat) and the reply endpoint, and the transport sets the actor, never a model argument. Routine requests send automatically; every other message waits for approval. An approval binds to a hash of the exact artifact shown, the lead revision and the ruleset, so a stale browser cannot approve changed content.

**Fact ledger.** Every value is an observation with a source: `submitted`, `fetched`, `derived`, `assumed`, `reply` or `underwriter`. An underwriter ruling outranks everything. A reply fills a missing producer field directly; a reply that differs from an existing value waits as a pending review and changes nothing until the underwriter approves it. A reply never sets a system-owned field. Event rows rebuild the effective facts.

**The send path's promise.** An intent moves `draft`, `dispatching`, `sent` (or `unknown`). The state `dispatching` commits before the mailbox post, and the post runs outside any transaction. After an ambiguous result the system lists the lead's emails and matches the intent id; with no match it opens a `delivery_unknown` item. The one promise is that nothing resends automatically after an ambiguous delivery. The mailbox has no idempotency key, so exactly-once delivery is not claimed. A lead with an open `delivery_unknown` sends nothing automatically.

**Skills as workflow steps.** A skill is a folder with a manifest (purpose, trigger, command classes it may issue, fallback), an entry point, and cases or a prompt where it has them. Seven steps are code and two use the language model (`polish_message`, `read_reply`). The model never writes a question: code renders every request from the ask plan, and the model writes only an opening and a closing that two checks hold to adding no consequence, price, deadline or request. A command that sends refuses a class the issuing skill's manifest does not declare. There is no agent framework and no model-driven control flow outside the chat.

**The chat is a second client.** It answers from the event log and cites event ids, and it can only propose: a directive becomes a card the underwriter previews and applies. A directive to approve, reject or send is refused, and the answer points to the lead's open item.

**Record and replay.** A model exchange is keyed by the skill, the hash of its prompt and forced tool, and the content the model is shown. Recordings are committed under `recordings/`, and they are the only model answers the tests and the replay demo see. Changing a prompt or tool changes the key, so its recordings are recorded again.

For the rest (rules core, the interpretation table, ledger rules, message classes, appendices) see `docs/architecture.md`; the reviewer's counterweight is `docs/critique.md`, dispositioned in its section 16.

## The eval loop

`make eval` replays the recorded model answers against the eval containers' own leadgen and mailbox and appends a row to `evals/results.jsonl`. Three suites exist:

- `seed42`: the ten leads against the ten labels in `evals/labels/seed42/`, graded at the settle point and again after scripted underwriter actions. The labels were written from the playbook, the registry and the data files without reading the rules code.
- `replies`: nine reply fixtures (three held back under `fixtures/replies/held/`) read by `read_reply`, graded against `evals/labels/replies/`.
- `chat`: three cases with eight recordings; a question causes zero commands, and a refused directive stays refused when reworded.

**The nine graders.**

- Coverage: every lead has a next action or is terminal, with the expected status, items and not-evaluated notes.
- One open request: at most one unanswered request per lead, and no duplicate send.
- Asks: the delivered asks equal the expected asks, none missing and none extra.
- Forbidden asks: nothing system-owned, bind-only or inactive is asked.
- Rule trace: every decline and requirement has a trace, and the path matches the label.
- Packet fidelity: every effect in the plan appears in the delivered packet.
- Send safety: a crash after mailbox acceptance, and an empty query while a send is in flight, each yield no second message.
- Stand's key: the generator's own debug history, regenerated in process, agrees with the system's asks.
- Reply reading: extraction and classification against the fixtures.

The runner also grades reply facts and chat, and four critical errors fail a run whatever the graders say: a duplicate send, an unauthorised send, a requirement missing from a delivered packet, and a reply approving an action.

**Three controls**, each a deliberately broken run that a named grader must fail: do nothing (Coverage), email every lead with every missing field (Forbidden asks and Asks), and send twice (Send safety and One open request, and the duplicate-send critical error). The log holds a scored row for each.

**Stand's answer key.** The grader checks every record of the generator's debug history for seed 42, outside `src/`. Allowed disagreements are counted and pinned in `evals/labels/seed42/exemptions.yaml`: 26 records exempt because lead 000 is a proposed decline, and 0 exempt as blocked. The run counts 190 agreeing records, 5 inactive conditionals, 1 field set again by a conflict injection and 0 disagreements. One record is decided by this submission's reading of the registry, not Stand's; it is counted apart.

**The results log.** `evals/results.jsonl` is append-only. A `run` row holds the suite, control, mode, commit, evaluator hash, case-set id, skill digests, scores, critical errors, tokens, cost and the hypothesis. A `decision` row, written by a person after reading a run, names keep or discard and the reason.

**The one improvement cycle.** On the held-back reply for lead 005 the model returned the state as "Colorado", and the `replies` suite failed it. One prompt clause (return the shortest conventional form) made the rerun return the short form; the remaining classification misses were not a prompt fault, so code now decides `answers_all` from the open asks, and the final run read 8 of 8 fixtures. Brett's `decision` row keeps the change; two earlier rows run on an uncommitted tree carry decision rows that discard them.

**What to iterate on next.**

1. `polish_message` has no cases and no repeat check. Its judge call decides whether an opening and closing add a consequence; measure its consistency across repeats and build a case table of rewrites it should reject.
2. Reply reading on confirmations and catalogue questions. The reply suite's nine fixtures are mostly field answers; add fixtures where the producer restates, corrects or partly answers a confirmation, and extend the held-back set.
3. Jev's confidence. The 0.7 threshold is the architecture's default and no Jev recordings are committed, so replay never exercises the cascade; record Jev's probabilities over the four classifications and set the threshold from them.
4. Lead 008's recorded `read_reply` call reports 391 input tokens on its second recording against 1,165 on the first, for the same input. The cause is unexplained.

Live-call totals recorded in `docs/progress.md` through milestone 4: 27,506 input and 6,896 output tokens on `deepseek-flash` across `read_reply` and the chat recordings.

## Skills

DeepSeek (`deepseek-flash`) is the language model. The cases column gives where a skill's cases live; a dash means plain unit tests and the seed-42 graders cover it, and the skill has no eval status.

| Skill | Model or code | Fires when | Fallback | Cases |
|---|---|---|---|---|
| `triage_fields` | code | a lead is received or its facts change | none | - |
| `resolve_data` | code | a field's resolution is derive, fetch or assume | none | - |
| `evaluate_playbook` | code | after resolution | none | `src/uwh/skills/evaluate_playbook/cases/` (one table per page) |
| `plan_asks` | code | after evaluation | none | - |
| `render_message` | code | an ask plan or a proposed decline needs a message | none | - |
| `polish_message` | language model | a request has been rendered | the rendered request is sent as it is | - |
| `read_reply` | language model; Jev classifies first when its key is set | a reply is delivered | the reply goes to the underwriter unread | `src/uwh/skills/read_reply/cases/` |
| `build_quote_packet` | code | no open blockers and no asks remain | none | - |
| `chat` | language model | the underwriter sends a chat message | the panel says the assistant is unavailable | `src/uwh/chat/cases/chat.yaml` |

A skill with a pass threshold (`evaluate_playbook`, `read_reply`, `chat`) has its cases scored in every run row. A model skill uses its fallback when the model is missing or its answer is rejected.

**Hit list**, in the order proposed: (1) the five unbuilt playbook pages, because Plumbing and Electrical apply to every lead and carry only a note; (2) real provider adapters in place of the stand-in lookups, since fetched values are the largest source of facts the producer is spared from; (3) a rule-change flow with eval evidence, so a reviewed ruling becomes a case.

## Cut and why

The brief sets a 5 to 6 hour box and grades what is cut. A lead that would have reached a cut playbook page carries a `not_evaluated` note naming it, never a silent pass.

- **Plumbing, Electrical, Pools, Trusts & LLCs, Protection Class 9 & 10.** No seed-42 lead reaches them, so their rules, wording and cases would be untested code. Plumbing and Electrical apply to every lead, so every packet carries their not-evaluated note.
- **The MCP transport.** The chat calls the same functions the pages use; a transport adds a protocol and no behaviour.
- **The 50-seed sweep.** The system and its evals run seed 42, whose ten leads carry the failure modes the brief names.
- **The rule-change flow and the model-driven triage comparison.** Rules change by a reviewed commit to the data files, which keeps one reviewed table.
- **Settings screens, the skills screen and the emergency stop.** Autonomy levels are constants in code: a routine request sends automatically and everything else waits for approval.
- **Server-sent events.** The pages refetch after an action and on an interval, which is enough for ten leads.
- **Controls and graders beyond the named ones.** The three controls and nine graders cover each failure the plan names.
- **The constructed packet cases and the outcome-case sample.** Cases are a table per page.

Known limits, recorded in `docs/progress.md`:

- A post in flight when a run is replaced may still reach the mailbox; every commit checks its run id, so the work writes nothing else.
- A stale browser tab after a new run is refused on an item it does not know.
- Paths no seed-42 lead reaches stop with a stated `data` blocker: the KYC range validator and its identity-score reviews, and the no-contact-route item.
- Round 2 goes beyond the fixtures: the reply fixtures answer a first request, so a second round has no fixture reply.
- No pricing or rating, no live third-party data (addresses are synthetic), and reply text comes from fixtures or the paste box, not a simulator.

## Where things are

- `src/uwh/`: the application. `runtime/` (event log, ledger, commands, send path, workflow), `rules/` (registry loader, validators, graph interpreter, reviewed data files), `skills/` (one folder each), `providers/` (stand-in lookups from captured world files), `chat/`, `api/` (FastAPI routes).
- `web/`: the React queue, detail pane and chat panel.
- `evals/`: the runner, graders, controls, labels and `results.jsonl`.
- `recordings/`: committed model exchanges; `fixtures/replies/`: producer replies for the fixture control.
- `tests/`: fast, slow and integration tests; `tools/` and `scripts/`: the fresh-clone rehearsal, type generation and the discipline check.
- `docs/`: `architecture.md`, `plan.md`, `critique.md`, `progress.md`, `acceptance.json`; `docs/brief/` and `docs/playbook/` are Stand's source material.
- `sim-harness/`: Stand's leadgen and mailbox, unmodified.
