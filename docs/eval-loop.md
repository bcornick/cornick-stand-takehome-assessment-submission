# The eval loop

**In one line:** the eval loop turns every mistake into a permanent test and checks every change against the full suite, so the agent improves as fixes build up without breaking what already works. Underwriters' overrides are the supply of new tests.

This page covers how the loop works, a real cycle from this project, what it measures and why the results can be trusted, how it leads to automated improvement, and its current limits.

## How it works

The agent's behaviour comes from three things you can change:

- **Rules:** the playbook pages, as decision trees in YAML (`src/uwh/rules/data/graphs/`). They decide each lead's path.
- **Prompts:** what the model is told when it reads a reply, softens an email or answers the underwriter.
- **Settings:** thresholds, such as the confidence at which Jev's reading of a reply is used.

The loop does not tune or retrain anything by itself. It makes every change to these three **measurable and safe**: after a change you know whether you fixed what you meant to fix, and whether you broke anything else.

```
 a mistake is found ──> it becomes a case with the right answer
        ▲                                │
        │                                ▼
 keep or discard  <──  rerun the whole suite  <──  one change, with a stated hypothesis
 (a decision row)          (make eval)              (rule, prompt or setting)
```

Without evals, someone changes a prompt, checks a lead or two by eye, and hopes. With evals, every change runs against the same known-correct answers, and the result is recorded next to the commit that produced it.

## A real cycle from this project

The first runs of the reply suite (`evals/results.jsonl`) failed three cases. Each failure got its own hypothesis in the log, and only one was a prompt problem:

| Failure | Hypothesis | Fix | Where the fix belonged |
|---|---|---|---|
| Lead 005: the reply said "Colorado, CO"; the model returned "Colorado", and the registry expects "CO" | The prompt does not say which form to return when a reply gives several | One prompt clause: return the shortest conventional form | The prompt |
| Leads 003 and 005: replies that answered everything were read as answering only part | The model cannot see which follow-up questions its own answers made unnecessary | Code decides "answers all" or "answers some" from the questions still open | Code, not the model |
| Lead 004: a reply that restated a value left the conflict about it open | A restating reply should close the conflict | A code fix to how conflicts close | Code |

The next run read all eight replies correctly. Brett's decision row keeps the change. Two rows from runs on uncommitted code carry decision rows that discard them, because their commit does not name the code that ran.

Two lessons. First, all three cases stay in the suite, so if a later change brings "Colorado" back, the eval catches it. Second, the eval showed where each fix belonged: a prompt tweak would not have fixed the other two.

## What it measures

A grader is a plain Python function that reads the real mailbox and the app's database after a run (`evals/graders/`). The brief's example questions map to named graders:

| The brief's question | Graders | What fails |
|---|---|---|
| Did it pick the right path? | **Coverage**, **Rule trace**, **Stand's key** | A lead at the wrong status or outcome, a decline or requirement reached through the wrong rules, or an ask Stand's own generator disagrees with |
| Is the follow-up correct and minimal? | **Asks**, **Forbidden asks**, **One open request** | A missing question, an extra one, a question about a field the producer does not own or that is only needed at binding, or a second open request on a lead |
| Did it avoid unnecessary escalation? | **Coverage** | An underwriter card the label does not expect fails, as a missing one does |
| Does the quote say what the plan decided? | **Packet fidelity** | A requirement or exclusion in the plan that is missing from the sent quote |
| Is sending safe? | **Send safety** | A second email after a simulated crash, or after an empty mailbox check while a send is in flight |
| Are replies read correctly? | **Reply reading** | A wrong value, a wrong reply type, or the lead in the wrong state after the reply |
| Does the assistant stay in its lane? | **Chat** | A question that changes anything, an instruction carried out instead of becoming a card, or an answer that cites nothing it was shown |

Four **critical errors** fail a run whatever the graders say: a duplicate send, a send without approval, a requirement missing from a sent quote, and a reply that approves an action.

## Why the results can be trusted

- **The answers come from outside the code.** The ten lead labels (`evals/labels/seed42/`) were written from the playbook and Stand's field registry without reading the rules code, and Brett signed each one. The code cannot grade itself.
- **Stand's own answer key.** The lead generator's record of what it broke in each lead is regenerated and checked record by record: 190 agree and none disagree. The allowed exemptions are pinned in `evals/labels/seed42/exemptions.yaml`.
- **Held-back cases stop overfitting.** Three of the eight producer replies (`fixtures/replies/held/`) were never shown to whoever built the reply reader. Tuning until the known cases pass is easy; the held-back ones show whether a fix generalises.
- **The graders are proven to fail.** A grader that never fails proves nothing, so three controls run the system broken on purpose, and each must be caught:

  | Control | What it breaks | Caught by |
  |---|---|---|
  | Do nothing | No lead is processed | Coverage, among others |
  | Email everything | Every missing field is asked for, owned by the producer or not | Forbidden asks and Asks |
  | Send twice | Every message is posted twice | Send safety, One open request, and the duplicate-send critical error |

- **Runs are repeatable.** Model answers are served from recordings, so the same code always gives the same score. If a score moves, a change moved it, not model randomness.
- **The log is the memory.** Each row in `evals/results.jsonl` holds the commit, a hash of the graders, the case set, each skill's prompt version, the hypothesis, the scores, the critical errors and the tokens. `make eval` refuses to run on uncommitted code, so every row names the code it measured. A person reads the run and adds a decision row: keep or discard, and why.

## Running it

```
make eval                                   # the ten leads
make eval ARGS="--suite replies"            # reply reading
make eval ARGS="--suite chat"               # the assistant
make eval ARGS="--control send_twice"       # a deliberately broken run
```

Each run starts fresh copies of Stand's lead generator and mailbox, loads the ten leads, and grades the first pass. It then plays scripted underwriter actions and producer replies, grades again, and appends a row to the log. Each playbook page, reply reading and the assistant also have case tables, scored in every run against a pass threshold. A run takes under a minute once its image is built, and needs no keys.

## From mistakes to automated improvement

### The signal is already recorded

Every underwriter decision is a typed event in the app's log, with its reason. Each event carries the lead's revision and the ruleset in force, so the exact situation can be rebuilt as a test. Each kind of override says something specific:

| The underwriter... | Recorded as | It becomes a case for... |
|---|---|---|
| edits an email before sending | `draft_edited`, with the full edited text and the reason | how requests and quotes are written |
| rejects a value read from a reply | `approval_recorded` (reject) on the review item | reply reading |
| discards a drafted request | `approval_recorded` (reject) on the request | what to ask, and when |
| withdraws a proposed decline | `approval_recorded` and `ruling_recorded`, naming the rules overridden | the playbook rule that declined |
| decides a playbook choice | `ruling_recorded`, with the option and the reason | the next layer of the playbook: the same ruling on similar facts suggests a new rule |
| (nothing: a model answer was rejected or missing) | `skill_fallback_used` | the skill's failure rate |

### Today: a manual loop

A person notices a mistake, writes the case and its right answer, makes one change, runs `make eval`, and records the decision. That is the cycle above. It works, but it depends on someone looking.

### Next: an automated loop

Each step builds on what is already recorded. This is a design; none of it is built.

1. **Harvest.** A scheduled job reads new override events and turns each into a candidate case: the situation rebuilt from the event, and the underwriter's answer as the expected result.
2. **Confirm.** An underwriter confirms each candidate's answer in one click. Labels stay human: the system never decides what "correct" means.
3. **Propose.** An improver agent reads the failing cases, the skill's prompt or the rule involved, and the log's history. It proposes one change with a stated hypothesis, on a branch.
4. **Gate.** `make eval` runs on the branch. The change passes only if the new cases pass, every existing case still passes, the held-back cases do not get worse, the controls are still caught, and the cost per lead stays within budget.
5. **Ship by risk.**
   - A wording or prompt change that passes everything can merge on its own.
   - A change to a rule or a threshold always needs an underwriter's sign-off, because it changes who is declined or what is asked.
6. **Watch.** The new version first runs in shadow beside the current one on real leads. Wherever the two disagree, an underwriter looks before it replaces the current one.

### What "better over time" means

The measures to track, run over run:

- **Override rate** per skill: the share of drafts, readings and plans the underwriter changes. This is the main measure; it should fall.
- **Unnecessary escalations per lead:** cards the underwriter clears without changing anything.
- **Asks per request and rounds per lead:** shorter and fewer means less back-and-forth with producers.
- **Time to quote**, and the **fallback rate** of each model skill.
- **Cost per lead**, so a quality gain that costs too much shows up.

### Guardrails

- The improver agent never sees the held-back cases, and they are rotated as the set grows.
- Only people write or confirm labels.
- The controls run in every gate, so a weakened grader is caught.
- One change per run, with its hypothesis, so a score change is attributable.
- Every keep or discard is a decision row in the log.

## Current limitations

- **It catches failures; it cannot measure rates yet.** One seed, ten leads and eight replies reliably catch the failure modes the brief names, but cannot say "reply reading is 94% accurate". That needs more seeds and more replies.
- **Overrides are not harvested yet.** The events are recorded, but labels and cases are still written by hand. One improvement cycle is recorded in the log.
- **The graders read the recorded asks, not the email text.** An email whose body dropped a question would still pass Asks and Forbidden asks.
- **The email rewrite has no cases.** `polish_message`'s judge has not been checked for giving the same verdict when run repeatedly. Replay cannot measure this, because a recording gives one answer every time.
- **A changed prompt needs live calls before it can be graded.** Replay covers only recorded prompts, so a new prompt must be recorded first.
- **The app does not check a skill's eval status before using it.** The results log is read by `make eval` and by people.
- **Cost undercounts.** Stored input-token counts leave out DeepSeek's cached input.

## Next steps, in order

1. **Harvest overrides into candidate cases.** This is the smallest step toward automation, because the data is already recorded.
2. **Grade the email text** against the plan, not only the recorded asks.
3. **Give the email rewrite cases,** and run its judge repeatedly in live mode to measure consistency.
4. **More seeds and more replies,** including replies that correct a value, answer only part of a question, or argue with a requirement. Stand's answer key grades other seeds without hand-written labels, which turns pass or fail into rates.
5. **An improver agent for prompts,** behind the gate above.
6. **Shadow runs and an override-rate dashboard.**
7. **A rule-change flow** with the underwriter's sign-off, so a repeated ruling becomes a reviewed rule with a case behind it.
