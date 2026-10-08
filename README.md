# Underwriting triage on a skill-and-eval harness

Brett Cornick's submission for the Stand Insurance take-home (`docs/brief/agentic_uw_takehome.md`). The app takes the ten seed-42 leads from Stand's lead generator and drives each one to a sent quote, one sent request to the producer, or a clear question for the underwriter. Nothing that quotes or declines a lead goes out without the underwriter's approval.

- `ARCHITECTURE.md`: the systems, the flow of a lead, where the model is used, and the trade-offs. A few minutes' read.
- `DEMO_GUIDE.md`: the demo, step by step.
- `docs/build_logs/`: the full design spec, the plan, the progress log and the full list of known limits.

## Run it

You need Docker (Compose 2.20 or later) and `uv`.

```
cp .env.example .env
make up
```

Open `http://localhost:8000` (the first build takes a few minutes), click **Load today's leads** in **Demo controls** at the bottom right, and follow `DEMO_GUIDE.md`.

**Keys.** None are needed. The default mode, `replay`, serves every model answer from `recordings/`, so the demo runs the same way every time. To use the models live, set these in `.env` and run `make up` again:

- `RUN_MODE=live`
- `MODEL_API_KEY`: a DeepSeek key
- `TYPESAFE_API_KEY` (optional): turns on Jev for reading replies; without it, DeepSeek reads them

In replay, the assistant answers only its three example questions; live mode answers anything.

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

**5. Integrations.**

| Service | What it gives | Status |
|---|---|---|
| Stand's lead generator and mailbox | the queue, email out, replies tracked | connected |
| DeepSeek (`deepseek-flash`) | reads replies, softens request wording, answers the assistant's questions | connected |
| Jev (TypeSafe) | a first reading of each reply, with a confidence | connected, optional |
| Replacement cost, Verisk PPC, identity screen, Stand's fire model and geospatial data, Stand's policy systems | replacement cost, protection class, KYC score, fire probability, slope, neighbour distance, vegetation, road access, broker tier | stand-ins |

A stand-in answers from data captured for seed 42 and checks the inputs a real lookup would need: with no street address, the address lookups report blocked. Replacing the stand-ins with real services comes first on the hit list, because looked-up values spare the producer the most questions. A real inbox, in place of the paste box and the stored replies, comes next.

## Architecture

A fixed workflow in Python processes each lead. Code makes every decision; the language model only reads replies, softens request wording and answers the underwriter's questions. Every change goes through one command layer into an event log, so every value has a source and every decision has a reason. See `ARCHITECTURE.md`.

## The eval loop

`make eval` replays the recorded model answers against fresh copies of Stand's services, grades the run and adds a row to `evals/results.jsonl`.

- **Suites.** `seed42` grades the ten leads against labels written from the playbook without reading the rules code; Brett signed each one. `replies` grades how eight stored producer replies are read, three of them held back from development. `chat` grades the assistant: a question changes nothing, a refused instruction stays refused when reworded, and an instruction hidden in a reply is not followed.
- **Graders.** Coverage, One open request, Asks, Forbidden asks, Rule trace, Packet fidelity, Send safety, Stand's key and Reply reading. A duplicate send, an unapproved send, a requirement missing from a sent quote, or a reply that approves an action fails the run outright.
- **Controls.** Three deliberately broken runs, each caught by a named grader: doing nothing, emailing every missing field, and sending twice.
- **Stand's answer key.** The generator's own record for seed 42 agrees on 190 records and disagrees on none; the exemptions are pinned in `evals/labels/seed42/exemptions.yaml`.
- **One improvement cycle.** A held-back reply had the state read as "Colorado"; one prompt change made it "CO", and the rerun read all eight replies correctly. The log records the failing run, the change and the decision to keep it.

**What to iterate on next.**

1. Give `polish_message` its own test cases, and check that its judge gives the same verdict when run repeatedly.
2. Add replies that correct or only partly answer a question, and grow the held-back set.
3. Set Jev's 0.7 confidence threshold from more recorded replies, not the default.
4. Keep the assistant's conversations on the server, and let a card show what its action would change before it is applied.

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

AI coding agents (Claude Code) wrote the code, under the working rules in `AGENTS.md`. A lead session planned each milestone and read every diff. Builder agents wrote the tests first and then the code, and a separate reviewer agent read each finished milestone. Brett made the product and design decisions, reviewed the reading of the playbook, and signed the eval labels. That is why the repository is larger than a 5 to 6 hour project would be. The cut list above is what was left out on purpose.
