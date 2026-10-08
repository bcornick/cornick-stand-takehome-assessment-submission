# The eval loop

**In one line:** every mistake becomes a permanent test, and every change is checked against the whole suite, so fixes build up without breaking what already works. Underwriters' overrides supply the new tests.

## How it works

The agent's behaviour comes from three things you can change: **rules** (the playbook pages, as YAML decision trees), **prompts** (for reading replies, softening emails and answering the underwriter) and **settings** (such as Jev's confidence threshold). The loop does not tune anything by itself. It makes each change measurable and safe: you learn whether you fixed what you meant to fix, and whether anything else broke.

```
 a mistake ──> a case with the right answer ──> one change, with a hypothesis
     ▲                                                   │
     └──── keep or discard (decision row) <── rerun the whole suite (make eval)
```

## A real cycle

The first runs of the reply suite failed three cases, each for a different reason:

| Failure | Cause | Fix |
|---|---|---|
| Lead 005: "Colorado" returned where the registry expects "CO" | The prompt did not say which form to return | One prompt clause |
| Leads 003 and 005: full answers read as partial | The model could not see which follow-up questions its own answers made unnecessary | Moved that decision into code |
| Lead 004: a restating reply left a conflict open | A gap in how conflicts close | A code fix |

The next run read all eight replies correctly, and the decision row keeps the change. Only one failure was a prompt problem; the eval showed where each fix belonged. All three cases stay in the suite, so a regression is caught.

## What it measures

Graders are plain Python functions over the real mailbox and the app's database after a run (`evals/graders/`).

| The brief's question | Graders |
|---|---|
| Did it pick the right path? | **Coverage** (status, outcome), **Rule trace** (which rules decided), **Stand's key** (the generator's own record) |
| Is the follow-up correct and minimal? | **Asks** (nothing missing or extra), **Forbidden asks** (nothing the producer does not own or that waits for binding), **One open request** |
| Did it avoid unnecessary escalation? | **Coverage**: an unexpected underwriter card fails, as a missing one does |
| Is the quote right and the sending safe? | **Packet fidelity**, **Send safety** (no second email after a simulated crash) |
| Are replies read correctly? Does the assistant stay in its lane? | **Reply reading**, **Chat** |

A duplicate send, a send without approval, a requirement missing from a quote, or a reply that approves an action fails a run whatever the graders say.

## Why the results can be trusted

- **Correct answers come from outside the code.** The ten lead labels were written from the playbook without reading the rules code, and signed by the author. Stand's answer key agrees on 190 records and disagrees on none.
- **Held-back cases.** Three of the eight producer replies were never shown to whoever built the reply reader, so they show whether a fix generalises.
- **The graders are proven to fail.** Three broken runs are each caught: doing nothing (Coverage), emailing every missing field (Forbidden asks, Asks), and sending twice (Send safety and a critical error).
- **Runs are repeatable.** Model answers come from recordings, so a score only moves when a change moves it.
- **Every run is logged.** `evals/results.jsonl` records the commit, the graders' hash, the prompt versions, the hypothesis and the scores. `make eval` refuses uncommitted code, and a person adds a decision row for each run: keep or discard, and why.

Run it with `make eval`, or `ARGS="--suite replies"`, `"--suite chat"` or `"--control send_twice"`. It needs no keys and takes under a minute once built.

## From overrides to automated improvement

**The signal is already recorded.** Each underwriter override is a typed event with its reason and the lead's revision, so its situation can be rebuilt as a test:

| The underwriter... | Event | Becomes a case for |
|---|---|---|
| edits an email | `draft_edited` (full text and reason) | how messages are written |
| rejects a value read from a reply | `approval_recorded` (reject) | reply reading |
| discards a request or withdraws a decline | `approval_recorded`, `ruling_recorded` | what to ask, or the rule that declined |
| decides a playbook choice | `ruling_recorded` (option and reason) | the playbook's next layer: a ruling repeated on similar facts is a rule candidate |

**Today the loop is manual:** a person writes the case, makes one change, runs `make eval` and records the decision.

**The automated loop (designed, not built):**

1. **Harvest:** a scheduled job turns new overrides into candidate cases.
2. **Confirm:** an underwriter confirms each answer in one click. Only people decide what is correct.
3. **Propose:** an improver agent reads the failing cases and proposes one change, with a hypothesis, on a branch.
4. **Gate:** the change passes only if the new cases pass, no existing case breaks, the held-back cases hold, the controls are still caught, and cost stays in budget.
5. **Ship by risk:** a prompt change that passes everything can merge on its own; a rule or threshold change always needs an underwriter's sign-off.
6. **Watch:** the new version runs in shadow beside the current one before it replaces it.

The main measure is the **override rate** per skill, which should fall over time. Beside it: unnecessary escalations per lead, asks per request, rounds per lead, time to quote and cost per lead. The improver never sees the held-back cases.

## Current limits

- **It catches failures but cannot measure rates.** One seed, ten leads and eight replies are too few to say "94% accurate".
- **Overrides are not harvested yet;** cases are written by hand, and one cycle is recorded.
- **Graders check the asks recorded with an email, not its text,** so a body that dropped a question would pass.
- **The email rewrite has no cases,** and replay cannot test whether its judge is consistent.
- **A changed prompt must be recorded live** before replay can grade it.

## Next steps, in order

1. Harvest overrides into candidate cases: the data is already there.
2. Grade the email text against the plan.
3. Give the email rewrite cases and measure its consistency live.
4. More seeds (graded by Stand's answer key) and harder replies, to turn pass or fail into rates.
5. The improver agent, behind the gate.
6. Shadow runs and an override-rate dashboard, then a rule-change flow with underwriter sign-off.
