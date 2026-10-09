# Underwriting triage on a skill-and-eval harness

Brett Cornick's submission for the Stand Insurance take-home (`docs/brief/agentic_uw_takehome.md`). The app takes the ten seed-42 leads from Stand's lead generator and drives each one to a sent quote, one sent request to the producer, or a clear question for the underwriter. Nothing that quotes or declines a lead goes out without the underwriter's approval.

- `ARCHITECTURE.md`: the systems, the flow of a lead, where the model is used, and the trade-offs. A few minutes' read.
- `docs/eval-loop.md`: the eval loop and the plan for iterating.
- `docs/architecture-diagram.md`: diagrams of the system, a lead's life, a reply's round trip, the eval harness and the repository.
- `DEMO_GUIDE.md`: the demo, step by step.
- `docs/build_logs/`: the full design spec, the plan, the progress log and the full list of known limits.

## Run it

You need Docker (Compose 2.20 or later) and `uv`.

```
cp .env.example .env
make up
```

Open `http://localhost:8000` (the first build takes a few minutes), click **Load today's leads** in **Demo controls** at the bottom right, and follow `DEMO_GUIDE.md`.

**Keys.** The app runs in `live` mode by default and calls the models. Before `make up`, fill in `.env`:

- `MODEL_API_KEY`: a DeepSeek key
- `TYPESAFE_API_KEY` (optional): turns on Jev for reading replies; without it, DeepSeek reads them

**No keys?** Live mode without a key still loads the queue, but replies go to the underwriter unread and the assistant cannot answer. Set `RUN_MODE=replay` in `.env` instead. Every model answer then comes from `recordings/`, so the demo runs the same way every time with no network calls to a model. In replay the assistant answers only its three example questions. Run `make up` again after changing `.env`.

**Other commands.**

```
make check        # lint, types, fast tests, frontend checks (needs Node 22 and pnpm)
make test-slow    # integration tests; needs the containers running
make eval         # an eval suite in replay; ARGS="--suite replies", "--suite chat" or "--control do_nothing"
uv run python tools/fresh_clone.py   # clone, start with no keys, run the demo pass, clean up
```

Ports: the app is on 8000, Stand's lead generator on 8081 and the mailbox on 8025; `APP_PORT`, `LEADGEN_PORT` and `MAILBOX_PORT` move them. The fresh-clone rehearsal has run on macOS (arm64); Linux and Windows (WSL2) have not been tried.

## The five decisions

**1. When the system acts alone, and when it asks.** It acts alone where the playbook and Stand's field registry settle the answer: it checks fields, looks up or works out values, sends a routine request for missing information, reads replies, and sends one follow-up for anything a partial reply left out. It asks the underwriter about every decline, every quote, every playbook choice (such as a failed fire simulation), any request with a mitigation question, and any reply that contradicts a value on file. While an open choice could still decline a lead, it holds that lead's request, so the producer isn't asked to do work on a lead that may be declined. The underwriter's choices are stored with their reasons and outrank every other source.

**2. Queue orchestration.** All ten leads load at once and up to four are processed in parallel. Each ends with a list of what it is waiting on, and its next action is the most urgent item. The lead list shows leads waiting on the underwriter first, then those waiting on the producer, then finished ones, ordered by earliest effective date. A reply re-runs its lead from the top.

**3. Outbound messages.** One message per lead per round. It asks only for what the producer owns and the system cannot look up or work out. Code writes every question; the model adds only a friendly opening and closing, and checks reject any opening or closing that adds a question, a price or a deadline. A partial reply gets one follow-up for the rest. A lead has at most one open request, and after two rounds it goes to the underwriter.

**4. What the underwriter sees.** A lead list with a short tag on each row saying what is waiting and on whom. Each lead opens as a conversation: the first line says what the underwriter needs to do and why, then what the system did as plain sentences, with a card wherever the underwriter decides. Any line opens its evidence (the fact and its source, the playbook page, the email) in a side panel. An assistant answers questions from the record and turns instructions into cards; it cannot approve or send anything.

**5. Integrations.** What is connected, what is stubbed, and what I would wire in next.

| Service | What it gives | Status |
|---|---|---|
| Stand's lead generator and mailbox | the queue, email out, replies tracked | connected |
| DeepSeek (`deepseek-flash`) | reads replies, softens request wording, answers the assistant's questions | connected |
| Jev (TypeSafe) | a first reading of each reply, with a confidence | connected, optional |
| Replacement cost (such as Verisk 360Value), Verisk PPC, an identity screen, Stand's fire model and geospatial data, Stand's policy systems | replacement cost, protection class, KYC score, fire probability, slope, neighbour distance, vegetation, road access, broker tier | stubbed |

A stub answers from data captured for seed 42, and checks the inputs a real lookup would need: with no street address, the address lookups report blocked. Wiring these to the real services comes first.

**Next: data that removes questions to the producer.** On the first pass, the nine requests ask the producer 95 questions. About half (47) are facts about the property that a data service could answer instead:

| Data | Questions it could answer (times asked) | Example sources |
|---|---|---|
| Property records | stories (5), square feet (3), purchase date (3), lot size (2), structure type (2), year built (1) | ATTOM, Cotality (CoreLogic), county assessor data |
| Aerial imagery | roof shape (4), roof material (3), pool type (2), deck (1) | Moody's CAPE Analytics, EagleView, Nearmap |
| Fire protection | distance to a hydrant (4), fire department type (3), distance to the fire station (2) | Verisk PPC, hydrant and station locations from municipal GIS or OpenStreetMap |
| Address validation | zip (3), state (2), city (1); a complete address also unblocks the other lookups | Smarty, Google Address Validation |
| Building permits | water heater age (3), plumbing age (2), roof replacement year (1) | BuildZoom, Shovels (partial: only permitted work is recorded) |

Wiring one in means a change to field triage: today it asks the producer for every field the producer may edit, and would instead look the field up first and ask only when the lookup finds nothing. A looked-up value carries its source, as fetched values do today, and the producer can still correct it. What only the client knows is still asked: coverage amounts, trusts, animals, residents, dates of birth.

Two more would make the underwriter's day easier without removing questions:

- **Loss history** (LexisNexis C.L.U.E. Property): prior claims on the property, a standard underwriting check the playbook does not yet use.
- **A real inbox** (the producer's email through Gmail or Microsoft 365), so replies arrive on their own instead of through the paste box.

Most of these services are sold under contract with no public sandbox, so none is wired in for the proof of concept.

## Architecture

A fixed workflow in Python processes each lead. Code makes every decision; the language model only reads replies, softens request wording and answers the underwriter's questions. Every change goes through one command layer into an event log, so every value has a source and every decision has a reason. See `ARCHITECTURE.md`.

## The eval loop

`make eval` replays the morning against fresh copies of Stand's services. Nine graders check that each lead took the right path, that each email asks for exactly what is missing and nothing more, that nothing is escalated without need, and that nothing is sent twice or without approval. The truth comes from labels the author signed, Stand's own answer key (190 records agree, none disagree) and held-back producer replies. Three deliberately broken runs prove the graders can fail. Every run adds a row to `evals/results.jsonl`, and one recorded improvement cycle shows the loop at work.

The loop turns every mistake into a permanent test and checks every change against the whole suite, so fixes build up without breaking what already works. Every underwriter override is already recorded with its reason, which is the supply of new cases. `docs/eval-loop.md` explains the loop, a real cycle from this project, how it leads to automated improvement, and its current limits.

## Skills

| Skill | Model or code | Fires when | Fallback |
|---|---|---|---|
| `triage_fields` | code | a lead arrives or its facts change | none |
| `resolve_data` | code | a missing field can be looked up, worked out or assumed | none |
| `evaluate_playbook` | code | after the data is filled in | none |
| `plan_asks` | code | after the playbook | none |
| `render_message` | code | a request or a decline notice is needed | none |
| `polish_message` | model | a request has been written | the plain request is sent |
| `read_reply` | model, with Jev first | a reply arrives | the reply goes to the underwriter unread |
| `build_quote_packet` | code | nothing is left to ask or decide | none |
| `chat` | model | the underwriter asks something | the turn ends with an error |

`evaluate_playbook`, `read_reply` and `chat` also have case tables scored in every eval run.

**Hit list, in order.**

1. The five playbook pages not built, because Plumbing and Electrical apply to every lead.
2. Real data services in place of the stand-ins, because looked-up values spare the producer the most questions.
3. A way for an underwriter's ruling to become a reviewed rule change, with an eval case to back it.

## Cut and why

The brief sets a 5 to 6 hour box and grades what is cut. A lead that would reach a cut page carries a "not evaluated" note naming it, never a silent pass.

- **Five playbook pages** (Plumbing, Electrical, Pools, Trusts & LLCs, Protection Class 9 & 10): no seed-42 lead reaches them, so they would be untested code.
- **Settings screens and an emergency stop:** when to send alone is fixed in code.
- **More seeds:** the system and its evals run seed 42, whose ten leads carry every failure mode the brief names.
- **A rule-change flow:** rules change through a reviewed commit to the data files.
- **Assistant extras:** server-side chat history, streamed answers, and a preview of a card's effect.
- **A mobile layout:** this is a desk tool.

## Known limits

The ones a reviewer is most likely to meet; the full list is in `docs/build_logs/known-limits.md`.

- No pricing, and no live third-party data (the addresses are synthetic).
- Replies come from stored examples or the paste box, and only first-round replies have examples.
- An edited draft is not checked automatically for prices or decline reasons; the underwriter approves every edited draft.
- The graders check the asks recorded with each email, not the email text itself.
- In replay, the assistant answers only its three example questions.

## How this was built

The time-box decision was where to spend my hours: on the product decisions, the reading of the playbook, and the eval labels. AI coding agents (Claude Code) wrote the code under the working rules in `AGENTS.md`: a lead session planned each milestone and read every diff, builder agents wrote the tests first and then the code, and a separate reviewer agent read each finished milestone. The labels were written from the playbook without reading the rules code, and I signed them. The repository is larger than hand-written hours would make it; the cut list above is what was left out on purpose.
