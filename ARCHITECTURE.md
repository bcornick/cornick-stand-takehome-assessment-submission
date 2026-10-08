# Architecture

This page covers the pieces, how a lead moves through them, where the language model is used and why, and the main trade-offs. It takes a few minutes to read. The full design (contracts, tables, and the reading of each playbook rule) is in `docs/build_logs/design-spec.md`. Section numbers in code comments, such as "9.4" or "A.11", refer to that spec.

## The pieces

| Piece | What it does | Built with |
|---|---|---|
| App | Runs the workflow, stores every event, serves the API and the screen | Python 3.12, FastAPI, Pydantic, SQLite, `uv` |
| Screen | The underwriter's lead list, lead conversations, side panel and assistant | React, TypeScript, Vite, Tailwind, shadcn/ui, built into the app image |
| Language model | Reads replies, softens request wording, answers the assistant's questions | DeepSeek `deepseek-flash` through the Anthropic SDK, on DeepSeek's Anthropic-format endpoint |
| Jev (optional) | Classifies each reply first and gives a confidence | TypeSafe's Jev, over HTTP |
| Stand's services | The lead generator and the mock mailbox, unmodified | Docker Compose; eval runs get their own copies |
| Evals | Replays the morning and grades it | A small Python runner and graders, in `evals/` |

There is no agent framework. The workflow is ordinary code; the model is called at three fixed points, each with a fallback.

## How a lead moves

```
Stand's lead generator ──> workflow, up to 4 leads at once ──> drafts and cards
                               │                                     │
                               ▼                                     ▼
                     event log + fact ledger  <── commands <── underwriter, assistant, replies
                                                       │
                                                       ▼
                                              Stand's mailbox
```

1. **Load.** "Load today's leads" asks the lead generator for the ten seed-42 leads.
2. **Check the fields.** Each lead is compared with Stand's field registry. For every missing field the system decides how to fill it: look it up, work it out, assume it, ask the producer, or leave it until binding.
3. **Fill what it can.** Lookups (fire model, replacement cost, protection class and others) come from stand-ins that answer from data captured for seed 42. Derived values, such as roof class from roof material, are worked out in code.
4. **Apply the playbook.** Each playbook page is a small decision tree in YAML (`src/uwh/rules/data/graphs/`). The result is a plan: a decline, requirements, questions, or a choice for the underwriter, each traced to the rule boxes that produced it.
5. **Write the message.** Code chooses what to ask and writes every question. The model adds only a friendly opening and closing.
6. **Send or wait.** A routine request sends on its own unless an open choice could still decline the lead. Everything else becomes a card for the underwriter.
7. **Read the reply.** A reply arrives through the paste box or the demo's stored replies. Jev, then the model, classifies it and the model pulls out the values. The values go into the fact ledger and the lead runs again from step 2.
8. **Finish.** With nothing left to ask, the system drafts the quote packet. It goes out only when the underwriter approves it.

## Where the model is used, and why only there

| Skill | Model's job | If the model fails |
|---|---|---|
| `read_reply` | Read a free-text reply: what kind of reply, and which values it gives | The reply goes to the underwriter unread |
| `polish_message` | Write a friendly opening and closing around the code-written questions | The plain request is sent |
| `chat` | Answer the underwriter's questions from the record, or propose an action as a card | The turn ends with an error message |

Decisions stay in code because the playbook is written rules. Code makes each decision traceable to a rule and testable. The model is used where text is free-form: reading a producer's reply and making an email sound human.

## What keeps it safe

- **One way to change anything.** Every change is a typed command from a named actor: the workflow, the underwriter, the assistant or the reply endpoint. Nothing a model writes can approve or send.
- **Approvals match what was shown.** An approval is tied to a hash of the exact text, so a stale screen cannot approve a changed draft.
- **Every value has a source.** Each value is marked submitted, looked up, worked out, assumed, from a reply, or from the underwriter, and the underwriter's ruling wins. A reply that contradicts a value on file waits for review.
- **No double emails.** A message is marked as sending before it is posted. If the result is unclear, the system checks the mailbox and never resends on its own.
- **One open request per lead.** A second request goes out only after a reply.

## Record and replay

Each model exchange is stored under `recordings/`, keyed by the skill, its prompt and what the model was shown. In replay mode the demo and the evals use these answers, so they run without keys and give the same result every time. Changing a prompt changes the key, so that exchange is recorded again.

## Trade-offs

| Chose | Over | Why | Cost |
|---|---|---|---|
| A fixed workflow in code | an agent framework driving a model through tools | The playbook is written rules; "one message per lead" and approval before sending are easier to guarantee in code | Cases the rules do not cover go to the underwriter instead of being improvised |
| Code makes every decision; the model reads and writes words | a model on the decision path | Every decline and requirement has a rule trace and a test | The model's judgment is not used to fill gaps |
| Code writes the questions | model-written emails | No question is dropped, invented or reworded | Plainer emails, softened only by the opening and closing |
| An event log and a fact ledger in SQLite | a graph database per lead | Every value has a source, and the "why" is rebuilt from events | One process |
| Recorded model answers | live calls in tests and the demo | Repeatable evals and a keyless demo | A prompt change means recording again |
| DeepSeek `deepseek-flash`, with Jev classifying replies | a frontier model for every call | Cost and token efficiency: the model only reads and writes words, so a small model does; Jev classifies replies well, with a confidence the model does not give | Two calls per reply when Jev is on; a model hosted outside the US needs a data-handling review before production |

Section 17 of the design spec lists the other alternatives considered.
