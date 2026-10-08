# Underwriting triage on a skill-and-eval harness

Brett Cornick's submission for the Stand Insurance take-home (`docs/brief/agentic_uw_takehome.md`). The app takes the ten seed-42 leads that Stand's generator posts and drives each to a sent quote packet, one sent request to the producer, or a wait on the underwriter with a stated reason. Every send of a quote packet or decline notice waits for an underwriter's approval. `ARCHITECTURE.md` gives the architecture in a few minutes; `docs/build_logs/` holds the full design spec, the plan and the build log. `DEMO_GUIDE.md` walks through the demo step by step.

## Run it

Prerequisites: Docker with Compose 2.20 or later, and `uv`. The frontend builds inside the image. `make check` also needs Node 22 and pnpm (`corepack enable`); the acceptance commands in `docs/build_logs/acceptance.json` use `jq`.

```
cp .env.example .env
make up
```

Open `http://localhost:8000`. The first build takes a few minutes. Stand's leadgen answers on host port 8081 and the mock mailbox on 8025; `APP_PORT`, `LEADGEN_PORT` and `MAILBOX_PORT` move the three.

In **Demo controls**, bottom right, click **Load today's leads**, then follow `DEMO_GUIDE.md`.

### Run modes

`RUN_MODE` in `.env` picks the mode, and the demo controls always show it.

- `replay` (the default): every model and Jev exchange is served from `recordings/`. No key is needed and no model host is called. A request with no recording fails closed with a visible error; a Jev miss falls back to the language model. The composer is disabled in replay, with the note "Questions need live mode": a typed question needs a live model, and a `live` or `record` run answers it. The three example questions in the Queue conversation are recorded, so each answers in replay when asked first on the day as loaded.
- `live`: calls DeepSeek with `MODEL_API_KEY`. Nothing reads or writes a recording.
- `record`: as live, and each exchange is written to `recordings/`. Also set `RECORDINGS_ACCESS=rw`, because the folder is mounted read-only otherwise.

`MODEL_API_KEY` is a DeepSeek key; `MODEL_BASE_URL` and `MODEL_ID` default to the Anthropic-format endpoint and `deepseek-flash`. `TYPESAFE_API_KEY` switches on Jev, which classifies a reply first; with it empty the language model classifies every reply, and the system works fully without Jev. Lead 007's partial reply shows Jev at work (`DEMO_GUIDE.md`, step 7). Without `MODEL_API_KEY`, live mode records a delivered reply unread and raises an underwriter review.

### Commands

```
make check        # lint, types, discipline checks, fast tests, frontend checks
make test-slow    # slow and integration tests; needs the containers running
make eval         # one eval suite in the eval containers, in replay
uv run python tools/fresh_clone.py
```

`make eval` runs the seed-42 suite by default. Pass `ARGS="--suite replies"`, `ARGS="--suite chat"` or `ARGS="--control do_nothing"` for the others; `--jev` classifies with Jev from `recordings/jev` and needs `TYPESAFE_API_KEY`. The target refuses a working tree with uncommitted changes, because each result row names its commit, and appends a row to `evals/results.jsonl`.

`tools/fresh_clone.py` clones HEAD into a temporary directory, copies `.env.example` with no keys, brings the stack up in replay under its own compose project and ports, runs the first pass and the fixture replies, then removes everything. It clones committed files only. Platforms: the rehearsal has been run on macOS arm64. Linux amd64 and Windows with WSL2: not run. Images are defined for amd64 and arm64.

## The five decisions

The brief names five product decisions. In short:

**1. When the system acts alone, and when it asks the underwriter.** It acts alone where the playbook and the registry settle the answer, and it stops where judgment or a commitment is at stake.

- **Acts alone:** checks every field, looks up or works out what it can, sends a routine request for missing information, reads a reply, fills missing fields from it, and sends one follow-up for anything a partial reply left out.
- **Asks the underwriter:** every decline, every quote, any request with a mitigation question, every playbook choice (such as a failed fire simulation), a reply that contradicts a value already on file, a reply it could not read, and an email the mailbox did not confirm.
- **Holds a request** while an open choice could still decline the lead, so the producer is not asked to do work on a lead that may be declined.
- **Keeps the underwriter's input:** each choice and ruling is stored with its reason and outranks every other source of a value. An approval is tied to the exact text shown, so a stale screen cannot approve changed content.

**2. Queue orchestration.** Loading posts all ten leads, and up to four run at once. Each lead runs the same steps in order and ends with a list of what it is waiting on; its next action is the most urgent one. The lead list puts leads waiting on the underwriter first, then those waiting on the producer or on data, then finished ones, each group by earliest effective date. A reply re-runs its lead from the top. A lead has at most one open request, and after two rounds it goes to the underwriter.

**3. Outbound messages.** One message per lead per round.

- It asks only for what the producer owns and the system cannot look up or work out. It never asks for system-owned or bind-only fields; the Forbidden asks grader checks this.
- Code writes every question, grouped by section and numbered.
- The model writes only a friendly opening and closing. Two checks, one in code and one by the model, reject any opening or closing that adds a question, a consequence, a price or a deadline; when one is rejected, the plain version goes.
- A partial reply produces one follow-up for the rest, not one message per missing field.
- Quote packets and decline notices go only on the underwriter's approval.

**4. What the underwriter sees.** The lead list gives one row per lead, with a short tag saying what is different and who it waits on. Each lead is a conversation:

- Its opening line says what the underwriter needs to do and why.
- Below that, the conversation lists what the system did as plain sentences, with a card wherever the underwriter decides. Buttons name what they send ("Send decline notice", "Send quote").
- Every line opens its evidence in a side panel: the fact and where it came from, the playbook page, or the message.
- A choice card shows what each value means for the decision, such as "Fails: above 0.50".
- An assistant answers questions from the record, linking to what it read, and turns instructions into cards the underwriter applies. It cannot approve or send anything itself.

**5. Integrations.**

| Service | What it gives | Status |
|---|---|---|
| Stand's lead generator and mailbox | the queue in, email out, replies tracked | connected |
| DeepSeek (`deepseek-flash`) | reads replies, softens request wording, answers chat | connected; recorded for replay |
| Jev (TypeSafe) | a first reading of each reply, with a confidence | connected; optional |
| Replacement cost estimator | replacement cost | stand-in |
| Verisk PPC | protection class | stand-in |
| Identity and adverse-media screen | KYC score | stand-in |
| Stand's fire model and geospatial data | fire probability, slope, neighbour distance, vegetation clearance, road access | stand-in |
| Stand's policy and distribution systems | broker tier, existing Stand policy | stand-in |

A stand-in answers from data captured for seed 42 (`src/uwh/providers/data/world-42.json`) and checks the inputs a real lookup would need: with no street address, the address lookups report blocked. The stand-ins come first on the hit list, because looked-up values are what spare the producer the most questions. Next would be a real inbox, so replies arrive without the paste box or the fixtures.

## Architecture

```
Stand's leadgen --> run start --> workflow (per lead, bounded pool) --> skills --> drafts
Stand's mailbox <-- send path <-- command layer <-- underwriter UI, chat, workflow, reply endpoint
                                  event log + fact ledger (SQLite) under all of it
```

A fixed workflow in Python runs each lead through the same steps: check the fields against Stand's registry, fill what can be looked up or worked out, apply the playbook, then write the request or draft the quote. Code makes every decision. The language model (DeepSeek, with Jev in front for reply classification) only reads replies, softens request wording and answers the underwriter's questions. Every change goes through one command layer into an event log, so every value has a source and every decision has a reason. There is no agent framework.

`ARCHITECTURE.md` explains the pieces, the flow of a lead, where the model is used, what keeps sending safe, and the trade-offs, in a few minutes. The full design is `docs/build_logs/design-spec.md`.

## The eval loop

`make eval` replays the recorded model answers against the eval containers' own leadgen and mailbox and appends a row to `evals/results.jsonl`. Three suites exist:

- `seed42`: the ten leads against the ten labels in `evals/labels/seed42/`, graded at the settle point and again after scripted underwriter actions. The labels were written from the playbook, the registry and the data files without reading the rules code.
- `replies`: eight reply fixtures (three held back under `fixtures/replies/held/`; lead 008's reply, the ninth, is the demo's) read by `read_reply`, graded against `evals/labels/replies/`.
- `chat`: five cases with 18 recordings (the three example questions have 9 more), one a cross-lead question answered from the queue facts; a question causes zero commands, a refused directive stays refused when reworded, and a producer's reply that carries an instruction is read back without one being followed.

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

**The results log.** `evals/results.jsonl` is append-only. A `run` row holds the suite, control, mode, commit, evaluator hash, case-set id, skill digests, scores, critical errors, tokens, cost and the hypothesis. A `decision` row, written by a person or the lead after reading a run, names keep or discard and the reason.

**The one improvement cycle.** On the held-back reply for lead 005 the model returned the state as "Colorado", and the `replies` suite failed it. One prompt clause (return the shortest conventional form) made the rerun return the short form; the classification misses that remained were not a prompt fault: code decides `answers_all` from the open asks, and the final run read 8 of 8 fixtures. Brett's `decision` row keeps the change; two rows run on an uncommitted tree carry decision rows that discard them.

**What to iterate on next.**

1. `polish_message` has no cases and no repeat check. Its judge call decides whether an opening and closing add a consequence; measure its consistency across repeats and build a case table of rewrites it should reject.
2. Reply reading on confirmations and catalogue questions. The reply suite's eight fixtures are mostly field answers; add fixtures where the producer restates, corrects or partly answers a confirmation, and extend the held-back set.
3. Jev's confidence. The 0.7 threshold is the design spec's default, applied to three outcomes (on topic, off topic, declines to answer). The nine Jev recordings exercise the cascade in replay, where Jev classifies seven of the eight reply fixtures and the model the other; record more replies and set the threshold from their probabilities.
4. The assistant. Chat threads live in the browser; keep them on the server so a reload and a second reviewer see them. Give the assistant a dry-run lookup, so a card can say what its command would change before the underwriter applies it.
5. Token counts. `tokens_in` on an event is the provider's `input_tokens` alone; DeepSeek reports cached input separately, so the stored input counts undercount what a call read (lead 008's reading shows 135 input tokens for a prompt longer than that). Count cached input too and compare the totals with the provider's billing page.

Live-call totals are recorded per milestone in `docs/build_logs/progress.md`; the project used about 50,000 reported input tokens and 13,000 output tokens on `deepseek-flash`, and 4,771 input and 468 output on Jev, with the undercount above.

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
| `chat` | language model | the underwriter sends a chat message | the turn closes with an error in the conversation | `src/uwh/chat/cases/chat.yaml` |

A skill with a pass threshold (`evaluate_playbook`, `read_reply`, `chat`) has its cases scored in every run row. A model skill uses its fallback when the model is missing or its answer is rejected.

**Hit list**, in the order proposed: (1) the five unbuilt playbook pages, because Plumbing and Electrical apply to every lead and carry only a note; (2) real provider adapters in place of the stand-in lookups, since fetched values are the largest source of facts the producer is spared from; (3) a rule-change flow with eval evidence, so a reviewed ruling becomes a case.

## Cut and why

The brief sets a 5 to 6 hour box and grades what is cut. A lead that would have reached a cut playbook page carries a `not_evaluated` note naming it, never a silent pass.

- **Plumbing, Electrical, Pools, Trusts & LLCs, Protection Class 9 & 10.** No seed-42 lead reaches them, so their rules, wording and cases would be untested code. Plumbing and Electrical apply to every lead, so every packet carries their not-evaluated note.
- **The MCP transport.** The chat calls the same functions the pages use; a transport adds a protocol and no behaviour.
- **The 50-seed sweep.** The system and its evals run seed 42, whose ten leads carry the failure modes the brief names.
- **The rule-change flow and the model-driven triage comparison.** Rules change by a reviewed commit to the data files, which keeps one reviewed table.
- **Settings screens, the skills screen and the emergency stop.** Autonomy levels are constants in code: a routine request sends automatically unless an open choice could still decline the lead, and everything else waits for approval.
- **Stopping a chat turn.** A turn is a few bounded model calls and can write at most a card, so a closed tab lets it finish.
- **Server-side chat history.** Typed messages live in the browser and are lost on reload; the timeline above them is the event log, which persists.
- **Streamed answer text.** The answer is a field of a forced tool call, so it arrives whole; the lookups stream as steps.
- **A dry-run lookup.** A card states its command in words; the command layer checks it in full when the underwriter applies it.
- **A mobile layout.** The surface is for an underwriter's desk and is desktop only.
- **Controls and graders beyond the named ones.** The three controls and nine graders cover each failure the plan names.
- **The constructed packet cases and the outcome-case sample.** Cases are a table per page.

## Known limits

What is left as it is in this proof of concept, from the reviews and from `docs/build_logs/progress.md`.

- A post in flight when a run is replaced may still reach the mailbox; every commit checks its run id, so the work writes nothing else.
- A stale browser tab after a new run is refused on an item it does not know.
- Paths no seed-42 lead reaches stop with a stated `data` blocker: the KYC range validator and its identity-score reviews, and the no-contact-route item.
- Round 2 goes beyond the fixtures: the reply fixtures answer a first request, so a second round has no fixture reply.
- No pricing or rating, no live third-party data (addresses are synthetic), and reply text comes from fixtures or the paste box, not a simulator.
- The graders score each request from the ask ids stored on the intent, not from the delivered email text; a body that dropped a question would pass Asks and Forbidden asks.
- An edited draft is not checked for pricing, a decline reason or internal notes before it is sent; the underwriter approves every edited draft and sees its text.
- A chat turn that finishes after a new run has started writes its proposal card into the new run.
- Proposal-card ids restart with each run (item ids do not), so a stale tab's Apply can hit the new run's card with the same number.
- In the replay demo the assistant answers only the three example questions, each asked first in the Queue conversation on the day as first loaded; once the replies are delivered, or after another question, an example closes with "Questions need live mode". A `live` or `record` run answers any question.
- A citation proves the assistant was shown the item, not that the item supports the claim.
- Dismissing a proposal card writes outside the command layer and records no event.
- A round-2 rewrite runs inside the command's transaction, so a slow model call holds the write lock for other leads.
- The runtime does not gate a skill on its eval status; the results log is read by `make eval` and by people.
- `Reply facts` is scored on the seed-42 run beside the nine graders of the design spec.
- Stored input-token counts leave out cached input, so the budget totals undercount.
- Two reply tests and the deck-height test feed hand-made model readings to test the code after the model.

## How this was built

AI coding agents (Claude Code) wrote the code, under the working rules in `AGENTS.md`. A lead session planned each milestone and read every diff. Builder agents wrote the tests first and then the code, and a separate reviewer agent read each finished milestone. Brett made the product and design decisions, reviewed the reading of the playbook, and signed the eval labels. That is why the repository is larger than a 5 to 6 hour project would be. The cut list above is what was left out on purpose.

## Where things are

- `src/uwh/`: the application. `runtime/` (event log, ledger, commands, send path, workflow), `rules/` (registry loader, validators, graph interpreter, reviewed data files), `skills/` (one folder each), `providers/` (stand-in lookups from captured world files), `chat/`, `api/` (FastAPI routes).
- `web/`: the React surface: the lead list, the conversation with its cards and chat, the drill-down panel and the demo controls. The favicon in `web/public/` is Stand's mark, taken from standinsurance.com and used for this submission only.
- `evals/`: the runner, graders, controls, labels and `results.jsonl`.
- `recordings/`: committed model exchanges; `fixtures/replies/`: producer replies for the fixture control.
- `tests/`: fast, slow and integration tests; `tools/` and `scripts/`: the fresh-clone rehearsal, type generation and the discipline check.
- `DEMO_GUIDE.md`: the demo, step by step.
- `ARCHITECTURE.md`: the architecture in a few minutes.
- `docs/build_logs/`: the full design spec, the plan, the critique, the chat-surface design, the progress log and the acceptance checks. `docs/brief/` and `docs/playbook/` are Stand's source material.
- `sim-harness/`: Stand's leadgen and mailbox, unmodified.
