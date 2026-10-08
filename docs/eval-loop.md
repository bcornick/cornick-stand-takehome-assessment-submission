# The eval loop and how to iterate

The brief asks for an eval harness that measures the quality of the agent's actions, and a plan for improving them over time. This page covers what is measured, against what truth, how a run works, how we know the graders can fail, one improvement made with the loop, and what comes next.

## What it measures

Each brief question maps to named graders. A grader is a plain Python function that reads the real mailbox and the app's database after a run (`evals/graders/`).

| The brief's question | Graders | What fails |
|---|---|---|
| Did it pick the right path? | **Coverage**, **Rule trace**, **Stand's key** | A lead at the wrong status or outcome, a decline or requirement reached through the wrong rules, or an ask that Stand's own generator disagrees with |
| Is the follow-up correct and minimal? | **Asks**, **Forbidden asks**, **One open request** | A missing question, an extra question, a question about a field the producer does not own or that is only needed at binding, or a second open request on one lead |
| Did it avoid unnecessary escalation? | **Coverage** | An underwriter card the label does not expect fails, just as a missing one does |
| Does the quote say what the plan decided? | **Packet fidelity** | A requirement or exclusion in the plan that is missing from the sent quote |
| Is sending safe? | **Send safety** | A second email after a simulated crash, or after an empty mailbox check while a send is in flight |
| Are replies read correctly? | **Reply reading** | A wrong value, a wrong reply type, or the lead in the wrong state after the reply |
| Does the assistant stay in its lane? | **Chat** | A question that changes anything, an instruction that runs instead of becoming a card, or an answer that cites nothing it was shown |

Four **critical errors** fail a run whatever the graders say: a duplicate send, a send without approval, a requirement missing from a sent quote, and a reply that approves an action.

## Against what truth

- **Lead labels** (`evals/labels/seed42/`): the expected result for each of the ten leads, written from the playbook and the field registry without reading the rules code, and signed by Brett. They cover the first pass and the state after scripted underwriter actions.
- **Stand's answer key:** the lead generator's own record of what it broke in each lead, regenerated for seed 42 and checked record by record. 190 records agree and none disagree; the allowed exemptions (such as lead 000, a proposed decline that sends no request) are pinned in `evals/labels/seed42/exemptions.yaml`.
- **Reply labels** (`evals/labels/replies/`): the expected reading of eight producer replies. Three are held back (`fixtures/replies/held/`) and were not shown to whoever built the reply reader, so they test it rather than confirm it.
- **Case tables:** each playbook page has a table of inputs and expected outcomes (`src/uwh/skills/evaluate_playbook/cases/`), as do reply reading and the assistant. Each is scored in every run against a pass threshold.

## How a run works

```
make eval                                   # the ten leads
make eval ARGS="--suite replies"            # reply reading
make eval ARGS="--suite chat"               # the assistant
make eval ARGS="--control send_twice"       # a deliberately broken run
```

1. The runner starts fresh copies of Stand's lead generator and mailbox, apart from the demo's.
2. It loads the ten leads and lets them settle, serving every model answer from `recordings/`. No keys are needed and the result is repeatable.
3. The graders score the first pass.
4. It plays scripted underwriter actions and producer replies, then grades again.
5. It appends one row to `evals/results.jsonl`.

A row records the commit, a hash of the graders, the set of cases, each skill's prompt version, the scores, the critical errors and the tokens used. Two runs can therefore be compared knowing exactly what changed. `make eval` refuses to run on uncommitted changes, so every row names the code that produced it. After reading a run, a person adds a `decision` row: keep or discard, and why.

## Proving the graders can fail

A grader that never fails proves nothing. Three **controls** run the system deliberately broken, and each must be caught:

| Control | What it breaks | Caught by |
|---|---|---|
| Do nothing | No lead is processed | Coverage, among others |
| Email everything | Every missing field is asked for, owned by the producer or not | Forbidden asks and Asks |
| Send twice | Every message is posted twice | Send safety, One open request, and the duplicate-send critical error |

The latest rows show all three caught, and the reference run passing every grader.

## One cycle of the loop

The reply suite failed on a held-back reply for lead 005: the model returned the state as "Colorado" where the registry expects "CO". One prompt clause ("return the shortest conventional form") fixed it, and the rerun read all eight replies correctly. The log records the failing run and the passing rerun, and Brett's decision row keeps the change.

Every improvement follows the same steps: a failing case, one change, a rerun, and a decision row.

## How to iterate from here

**The loop in use.** Each underwriter override is a signal: a rejected draft, a changed decision, an edited email, a reply the reader got wrong. Each one becomes a case or a label once the underwriter confirms the right answer. The change that fixes it (a prompt, a rule or a threshold) is accepted only if the suite still passes and the new case does too. The playbook's next layer arrives the same way: an underwriter's ruling becomes a reviewed rule with a case behind it.

**Next, in order:**

1. **Grade the email text, not just its record.** The graders check the asks recorded with each email. A body that dropped a question would still pass, so parse the sent body and check it against the plan.
2. **Give the email rewrite its own cases.** `polish_message` has no case table, and its judge has not been checked for consistency. Run it repeatedly on the same input and build a table of rewrites it must reject.
3. **Harder replies.** Most reply fixtures answer plain questions. Add replies that correct a value, answer only part of a confirmation, or argue with a requirement, and grow the held-back set.
4. **Set Jev's threshold from data.** The 0.7 cut-off is a default. Record more replies and choose the threshold from Jev's confidence on cases with known answers.
5. **More seeds.** Every run uses seed 42. Running other seeds through Stand's answer key would find failure modes these ten leads do not have, without hand-writing labels.
6. **Track time per lead** beside the tokens and cost each row already holds, so a change that improves quality at too high a price shows up.

## Known gaps

- The graders read the asks recorded with each email, not the email text (item 1 above).
- One seed, ten leads and eight replies: enough to catch the failure modes the brief names, too few to measure rates.
- Stored input-token counts leave out DeepSeek's cached input, so recorded costs undercount.
