# Chat surface: the underwriter's conversation

## Purpose

The underwriter surface is a chat-first, three-column agent interface in the style of Claude, ChatGPT and Perplexity. The conversation is the central surface. Every claim drills down into its evidence. Demo-only controls live in a separate floating panel. Stand's branding is applied lightly.

This is a take-home submission for an Agentic Engineer role, graded on clean code and YAGNI. The builder goes vertical: one lead's conversation end to end before widening. This document governs the underwriter surface until its documentation changes land in `docs/architecture.md`.

| Value | Setting |
|---|---|
| Build time target | one to two days |
| Viewport | desktop only, at least 1280px wide |
| Left column | 280px |
| Right panel | 360px; 480px in the full-detail view |
| Model calls per turn | at most 8, validation retries included (`MAX_STEPS` stays 4 and `read_tool_input` retries once) |
| Exchanges sent with each message | the last 4 of the open conversation |
| Refetch interval | 5 seconds (`REFRESH_MILLISECONDS` in `web/src/App.tsx`) |
| Accent token | #601421 |

## Decisions already made

Brett, the owner, has approved this design. These rules hold throughout:

- Every state change is a typed command.
- The model never decides underwriting or executes anything. Its only write is a proposal card the underwriter applies.
- An approval binds to a hash of the exact artifact shown.
- A question yields zero commands.
- The message and every tool result are data, never instructions.
- Nothing in `src/` is left unused.

The shape of the surface is also settled. It is desktop only, with no drawer or sheet. Chat history lives in browser memory and is lost on reload by design. The answer arrives whole; only the lookup steps stream. A turn has no stop button. The queue page, the lead detail page and the items section stop being top-level pages: their sections become the lead list, the panel views and the inline cards.

## The surface

### Shell

- **Left column.** The name STAND in capitals, then the lead list. A "Queue" entry at the top of the list opens the queue-level conversation, whose greeting carries the run's counts.
- **Lead groups.** Waiting on the underwriter; waiting on the producer or data; finished. The groups and their order are the `group` field and the row order `GET /api/leads` returns. `GROUP_LABELS` in `web/src/labels.ts` carries the two relabelled names. The middle group includes data waits, so its label names them.
- **Lead row.** The lead's short name ("Lead 008"), address or "no address", and a chip that says what differs between leads: "Needs your decision", "Waiting on producer", "Waiting on data", "Quote sent" or "Declined". A second line reads "Effective Jul 21 · 2 days in queue", with the age in whole business days ("in queue today" under half a day) and "Past service level" when breached. A row shows "no address" when its `label` equals its lead id, which is what `lead_label` in `src/uwh/skills/steps.py` returns for a lead with no address.
- **Centre column.** The conversation, fluid width. Its header names the lead and holds the "Full detail" link.
- **Right panel.** The drill-down panel, collapsed until opened.
- **Polling.** The refetch keeps running during a turn and does not touch the turn's state. A closing `proposal` event triggers a refetch.

### Narrative

The centre column for a lead leads with the answer: one assistant message written by code (`LeadDetail.summary`, from `src/uwh/api/summary.py`: what the underwriter must do, then what the system waits on, or a finished lead's outcome and date), the open cards right after it, then the event-by-event timeline, oldest first, folded under "Show the work (N steps)", then the chat tail. The column is centred at 720px; assistant messages carry a small "Assistant" label and vertical spacing; bubbles and cards fill the column. Two text sizes: `text-sm` for content, `text-xs` for labels and meta.

- **Wording.** Code writes the timeline from the lead's events. `event_summary` in `src/uwh/api/event_summary.py` is rewritten once, server side, into plain sentences that name the fact, the result and the consequence. The narrative reads it through `GET /api/leads/{id}/events`, and so does the assistant's event lookup. A sentence names a field by its key; wherever a human reads one (the narrative, the cards, the facts table, the panel) the client replaces the key with the registry's label (`labelKeys`, `fieldLabel` in `web/src/format.ts`): "Fire probability 0.79", not `p_f`. `SUMMARY_LIMIT` in `src/uwh/api/leads.py` goes with `EVENT_LIMIT`: sentences are not cut. For example:
  - "Triaged the fields: 2 missing"
  - "Fetched the fire probability: 0.79"
  - "The fire simulation failed, so you need to choose"
- **Grouping.** Consecutive system events (the `workflow` actor, and the `inbound` actor's handling of a reply) form one assistant message with bullets; the underwriter's events stand apart. A message bubble, a card or the underwriter's event breaks the group. Within a message a run of fact events longer than three folds into "Recorded N facts", a run of provider lookups merges into one line ("Looked up 5 providers: 2 found, 3 blocked on city and zip", from `EventRow.lookup`) and repeated triage lines keep the last. Model calls, the rewrite checks, replay misses and injected faults are not narrated. A citation chip appears only where the panel shows more than the line: on a fact bullet and on a bubble; chips are numbered 1, 2, 3 within a message.
- **Bubbles.** A message the system sent (`message_sent`) and a reply it read (`reply_received`) render as bubbles. A bubble shows the subject where the event carries one, and folds the body.
- **Cards.** Workflow-raised items render inline at their `blocker_opened` event. They use the components in `web/src/lead/ItemActions.tsx` with their labels:
  Every card has one shape: its summary line; for a draft, a folded preview ("Preview the notice" or "Preview the packet") holding the text and, inside it, Edit; the choices as enabled buttons; and, once a choice is clicked, one reason field with a confirm that repeats the choice. Nothing is submitted without a reason.
  - draft review with Approve and Reject, and "Withdraw decline and send the asks" on a decline notice;
  - question, with the playbook's options as equal buttons;
  - pending observation, delivery unknown, event-raised review (Acknowledge) and persistent review.
- **Resolved cards.** A resolved card stays in place as one read-only line: the sentence and actor of the `approval_recorded` event naming its item, or of the `ruling_recorded` event whose `choice_id` is among the card's choices. A card closed with neither, such as a draft superseded on re-evaluation or a delivery re-checked, shows "Closed" and nothing else.
- **Hidden events.** Events with the `assistant` actor are not narrated: a turn's `proposal_created` and `command_refused` are shown by the card and the answer in the chat tail instead.
- **Confidence.** A reply reading shows Jev's confidence with its meaning. The threshold is the one `threshold()` in `src/uwh/skills/read_reply/jev.py` returns. A reading the model classified shows no confidence.
  - "Jev classified this reply (0.83, at or above the 0.70 threshold)"

### Chat tail

- **Content.** Below the timeline sit the underwriter's typed messages and the assistant's answers for this lead. They are held in browser memory, keyed by `RunView.run_id`, lead id and "Queue", and lost on reload by design. A new run clears them, because event ids restart with each run.
- **Proposal cards.** A card sits in the tail of the lead it targets. `ProposalView` gains `lead_id`, read from the card's `proposal_created` event through `proposals.event_id`; the `proposals` table has no lead column. `_lead_named` in `src/uwh/runtime/commands.py` resolves an `intent_id` to its lead, so an `edit_draft` card lands on its lead. Open cards are fetched from `GET /api/proposals`. A card with no lead sits in the queue conversation.
- **Queue conversation.** Its first assistant message is the greeting "3 leads need you. 7 are waiting on producers." (and "2 quotes sent." when any are), built from the run's counts. The open items across all leads follow as cards; each card loads its lead's detail, which the card components take. While nothing has been asked, three fixed example prompts sit beside the composer as buttons. Each prompt is a question, so none can propose:
  - "Which leads are waiting on me, and why?"
  - "Why is lead 000 a proposed decline?"
  - "What did we ask the producer on lead 008?"
- **Composer.** One line at the bottom, with the lead as its placeholder and the accessible label "Message". In replay it is disabled with the note "Questions need live mode".
- **History.** Each message carries the last exchanges of the open conversation as `history` on `ChatRequest`, so follow-ups like "why?" work. An exchange is the message and its reply text: the answer, the card's rationale, or the error. `ChatRequest.history` holds at most 4 entries, each capped at `MAX_CHAT_CHARACTERS` like `message`, and the prompt names `history` as data, never instructions, because earlier answers were written after reading reply text.
- **Cross-lead proposals.** A turn asked on lead A that proposes for lead B shows one line in A's tail, "Proposed on lead B", linking to B; the card sits on B.

### One chat turn

- **Transport.** `POST /api/chat` answers with a server-sent-events stream through FastAPI's native support (`fastapi.sse`, pinned at 0.142 in `uv.lock`). The route yields a discriminated union of Pydantic event models with a `type` field, which puts the union in the OpenAPI document; it does not set `event:` names. FastAPI writes a `: ping` comment line every 15 seconds. The browser reads the stream with `fetch` and a stream reader, not `EventSource`, and skips comment lines.
- **Thread.** The route runs the turn in one worker thread with its own connection from `runtime.database()`. The thread pushes events to a queue that the async response drains. `run_turn` takes a callback that receives each step.
- **Events.** The stream carries the events in the table below. Exactly one closing event ends it.
- **No streamed text.** The answer is a field of a forced tool call, so it arrives whole in `answer`.
- **In the browser.** The steps show live as a collapsible "what I looked at" list, with a working indicator until the closing event.
- **No cancellation.** There is no stop button. A closed tab lets the turn finish.
- **Refusals and failures.** A refused `approve` or `reject` closes with `answer`, pointing to the open item in the lead's conversation. A refused `start_run` answers "Loading leads is a demo control, bottom right." A refused `deliver_reply` answers "Paste the reply in the lead's full detail." A missing model key, a recording miss or a model API error closes with `error`. A malformed request keeps its 422.

| Event | Sent when | Carries |
|---|---|---|
| `step` | a lookup completes | the lookup's name in words and a one-line result summary, such as "Read the facts of lead 008: 14 values, 2 from the reply" |
| `answer` | closing | the text and the resolved citations |
| `proposal` | closing | the card id and its lead |
| `error` | closing | the reason |

### Lookups and citations

Named read functions in `src/uwh/chat/tools.py`, each over the views the pages use. They replace `lead_events`, `lead_summary` and `open_items` in `READ_TOOLS`, which they subsume. `EVENT_LIMIT` goes, so one lead's events are never capped.

| Lookup | Reads | A result item cites |
|---|---|---|
| Lead events | `lead_events` in `src/uwh/api/leads.py` | the event id |
| Lead summary | status, facts with sources, open items, from `lead_detail` | a fact: the event that set it (`observations.event_id`); an item: the event that opened it (`blockers.opened_event_id`) |
| Messages | requests sent and replies received on the lead | a request: its intent id; a reply: its `reply_received` event id |
| Playbook path | the plan's effects, waits and not-evaluated notes grouped by page | the lead plus the page key (`Graph.id`) |
| Current draft | the text of the lead's latest draft | its intent id |
| Queue summary | the run summary and the open items of every lead | an item: the event that opened it |

- **Reference numbers.** Every result item carries a turn-local reference number. The server keeps the map from number to lead id, kind and immutable id for the turn. The model sees numbers, never event ids.
- **Citing.** `ChatStep` names the six lookups, `answer` and `propose_command`; an answer cites reference numbers. The server keeps only citations that appeared in this turn's results and returns them resolved. This replaces the `shown_ids` check in `run_turn`.
- **Schema.** The chat response schema changes, so `web/src/api/openapi.json` and `web/src/api/types.ts` are regenerated. The route declares its event models in its OpenAPI response, so `tools/export_openapi.py` carries them.
- **Chips.** A citation renders as a numbered chip. A click opens the right panel on the cited thing.
- **Pages.** The stored plan holds no per-page record, so the playbook lookup and the page view group what the plan already holds by page key, which is `Graph.id`. An effect's page is the page number at the start of its `trace.board_path` (`04:ROOT`), mapped to the graph whose `page` path carries that number; a decline on every branch has an empty `board_path` and is grouped by its first branch's `board_path` in `trace.alternatives`; `undecided` names its graph; a `not_evaluated` note names a built page or a page with no graph (`plumbing`, `electrical`), and the latter is a page of its own with the note as its only content. Nothing re-walks a graph on read and the rules core does not change. A page view shows its effect lines (`effectLine` in `web/src/lead/DetailPane.tsx`), the board path ids, its waits and its notes; the facts a page read are not shown.
- **Current state.** A chip for a draft or a page opens the current draft or the current plan, labelled "current"; `edit_draft` and a re-evaluation change them under the same id. History is cited through events.

### Writes

- The only write is a proposal card.
- `is_proposable` in `src/uwh/runtime/proposals.py` refuses `start_run` and `deliver_reply`, as it refuses `approve` and `reject`. The proposable commands are `edit_draft`, `record_ruling`, `resolve_fact` and `decline_lead`.
- Both commands leave `src/uwh/chat/prompt.md` and `inWords` in `web/src/chat/ProposalCard.tsx`. The prompt's injection rule stays.
- `_point_to_the_items` in `src/uwh/chat/skill.py` points to the lead's conversation.

### Modes

- `live` and `record` run the turn against DeepSeek and stream its steps. `record` captures each exchange, as every model skill does.
- `replay` disables the composer. The endpoint closes with the `error` event at once, with the reason "Questions need live mode", and makes no model call.
- The chat eval suite calls `run_turn` directly with recordings (`play_chat_cases` in `evals/run.py`), so the endpoint's replay rule does not reach it. The suite is re-recorded once, after the change.
- The three example prompts are a server-owned list in `src/uwh/chat/`, exposed on `RunView` as `example_prompts`, which the client renders as buttons; nothing is duplicated in TypeScript. They get one replay attempt, at the end of milestone 2. If they replay cleanly in the fresh-clone rehearsal, the replay rule lets exactly those messages through and the buttons work in replay. Otherwise the buttons are disabled with the composer and the README says so.

### Drill-down panel

The panel opens on a citation chip or on a card's "details" link. One click closes it.

| View | Shows |
|---|---|
| Fact | value, source tag, when observed, the event that recorded it, the lead's other observations of the same key as history |
| Event | type, actor, time, payload in words, previous and next links |
| Message | subject where present, body, delivery state |
| Playbook page | its effect lines, its board path ids, its waits, its not-evaluated notes |
| Full lead | Waiting on (read-only), Facts, Plan, Messages, and the lead actions Paste a reply, Resolve fact and Decline lead; the cards act from the conversation, and the timeline is the record of what the system did |

- "Full detail" in the conversation header opens the full lead view at the wider width.
- The three forms of `web/src/lead/LeadActions.tsx` live in the full lead view. Only they act on a lead from the panel.
- The fact view takes the event that recorded the fact from `FactView.event_id` (`observations.event_id`), and the history from the lead's `fact_observed` rows with the same `fact_key`. A pending observation becomes effective later through its approval, so the view calls them observations, not replaced values.

### Demo panel

- A small card pinned bottom right, titled "Demo controls". It starts minimised, as a pill reading "Demo controls" that opens the card, and minimises again from the card.
- "Load today's leads" starts the run (`startRun`). When a run exists, an inline confirm says "This clears the current day".
- "Deliver the producers' replies" delivers the fixtures (`deliverFixtureReplies`). The card shows the run id, seed and mode from `RunView`.
- It is a separate component. With no run loaded, the product's empty state says so and points to it.

### Branding

- The name STAND sits top left in capitals, as text, in place of Stand's wordmark. Stand's favicon, taken from standinsurance.com, is served from `web/public/`. The page title in `web/index.html` is "Stand Underwriting".
- The README says in one line that the favicon is Stand's, used for the submission only.
- Buttons follow those of standinsurance.com: a pill in ink (#131311) with white text that lightens on hover, or an outlined pill whose border darkens on hover; a destructive button is the outlined one. One accent token colours the selected lead, citation chips and the working indicator. The conversation column sits on the site's beige (#f3f1e6) with its cards, bubbles and message box in white, and the demo controls are a card in the site's black (#06080b) with white text; the lead list and the panel stay white. Text is black on white with Tailwind greys otherwise. Geist stays.

## Behaviour the tests pin

Server:

- `tests/chat/test_skill.py`: a citation outside this turn's results is dropped.
- `tests/chat/test_skill.py`: a question yields zero commands.
- `tests/api/test_chat.py`: the stream ends with exactly one closing event.
- `tests/api/test_chat.py`: replay answers the live-mode error.
- `tests/api/test_chat.py`: `start_run` and `deliver_reply` are refused as proposals, with the two answers above.
- `tests/api/test_chat.py`: a proposal lands on its target lead.
- `src/uwh/chat/cases/chat.yaml`: the instruction-bearing reply `fixtures/replies/LEAD-00000042-001.txt`, read through the messages lookup, yields zero proposals.

The chat case asks "What did the producer reply on lead 001?" and expects `answer_with_event`; the chat grader's zero-commands rule covers the proposals. It needs lead 001's reply delivered, so `ChatCase` gains an `after_replies` flag, `play_chat_cases` runs flagged cases last, after the first pass and the fixture replies. The chat grader (`evals/graders/chat.py`, `tests/evals/test_chat.py`) reads the resolved citations in place of `cited_event_ids`: a cited answer is one with at least one resolved citation. For a multi-turn case, `play_chat_cases` sends the earlier turns as `history`, which is part of the recording key. `test_only_the_latest_events_are_shown` in `tests/chat/test_tools.py` is deleted with `EVENT_LIMIT`.

Browser:

- The narrative renders every event type.
- Cards appear at their event.
- A chip opens the right view.
- The demo panel's confirm blocks a second run.

The frontend tests are kept, rehomed or deleted according to whether their subject survives:

| Test | Fate |
|---|---|
| `web/src/App.test.tsx` | lead order and packet approval kept; the open-items test goes to the queue conversation; the fixture-replies test goes to the demo panel |
| `web/src/lead/DetailPane.test.tsx` | item tests kept against the inline cards; lead-action tests kept against the full lead view |
| `web/src/chat/ChatPanel.test.tsx` | apply, refused, dismiss and error tests kept; the cited-ids test becomes the chip test |
| `web/src/lead/EventList.test.tsx` | deleted with `EventList.tsx`; the narrative test covers its subject |

## Descoped on purpose

Each item is named in the README under "Cut and why" or "Known limits".

| Item | README section | Wording to add |
|---|---|---|
| Stop and cancellation | Cut and why | **Stopping a chat turn.** A turn is a few bounded model calls and can write at most a card, so a closed tab lets it finish. |
| Server-side chat history | Cut and why | **Server-side chat history.** Typed messages live in the browser and are lost on reload; the timeline above them is the event log, which persists. |
| Run-bound proposals; dismiss through the command layer | Known limits | Already listed; the wording stays. |
| Streamed answer text | Cut and why | **Streamed answer text.** The answer is a field of a forced tool call, so it arrives whole; the lookups stream as steps. |
| A dry-run lookup | Cut and why | **A dry-run lookup.** A card states its command in words; the command layer checks it in full when the underwriter applies it. |
| What a citation proves | Known limits | A citation proves the assistant was shown the item, not that the item supports the claim. |
| Mobile layout | Cut and why | **A mobile layout.** The surface is for an underwriter's desk and is desktop only. |

## Documentation changes

- **`docs/architecture.md` section 11.** Rewritten to describe this surface. "No numeric confidence is displayed" is replaced by "A confidence is shown only with its threshold."
- **The server-sent-events cut.** Removed from `docs/plan.md` "What is cut", from the README "Cut and why", and from `docs/architecture.md` section 4.1, which lists it too.
- **`docs/architecture.md` A.5.** The `POST /api/chat` row says the turn answers as a server-sent-events stream.
- **README walkthrough.** Rewritten for the demo panel and the conversation: "Load today's leads", lead 008's conversation, "Deliver the producers' replies", and the inline Approve.
- **README replay sentences.** The run-modes sentence and the known limit about the chat in replay say the composer is disabled in replay, with "Questions need live mode", unless the example prompts pass the replay attempt.
- **README sections.** "Cut and why" and "Known limits" take the wording above. "What to iterate on next" adds server-side threads and a dry-run lookup. The chat paragraph under "Architecture" and the `web/` line under "Where things are" name the conversation and the panel.
- **Chat skill wording.** The text in `src/uwh/chat/skill.py` that points to "lead X's detail pane" points to the conversation.
- **`docs/architecture.md` proposals.** The sentence that a proposal "cannot carry approve or reject" names the four proposable commands.

## Milestones

### 1. Server

- Rewrite `event_summary` into grouping-friendly sentences, with the Jev threshold wording. `tests/api/test_event_summary.py` keeps covering every event type.
- Extend the views. `EventRow` gains `item_id` on blocker and approval events and `fact_key` on `fact_observed`. It also gains `message`: the subject and body of a `message_sent` from its intent, and the body of a `reply_received` from its payload. `FactView` gains `event_id`. `ProposalView` gains `lead_id`.
- Write the six lookups and the reference map in `src/uwh/chat/tools.py` and `run_turn`.
- Add `history` to `ChatRequest`. Rewrite `src/uwh/chat/prompt.md` for the lookups, the reference numbers and the history.
- Change the proposable set in `is_proposable`.
- Build the SSE endpoint with `step` and the three closing events, the worker thread and the replay rule.
- Regenerate `openapi.json` and `types.ts`.
- Update the callers and tests the change reaches: `play_chat_cases`, the chat grader and its test, and `test_the_model_is_shown_the_message_the_lead_and_nothing_else`; delete `test_only_the_latest_events_are_shown`.
- Migrate `web/src/chat/ChatPanel.tsx` and its test to the stream and the new response shape, so `make check` passes at the end of this milestone; the rest of the surface waits for milestone 2.
- Add the chat case and re-record the chat suite once in `record`.

Done when: the server tests above pass, `make check` passes, and one lead's events render as readable sentences through the events endpoint.

### 2. Client

- Build the shell, the lead list with the "Queue" entry, and polling that leaves a turn's state alone.
- Build the narrative: grouping, bubbles, chips, cards at their event, and resolved cards.
- Build the chat tail: the stream reader, the steps list, the working indicator, the composer, history, and proposal cards by lead.
- Build the drill-down panel with its five views; edit `DetailPane.tsx` so the full lead view's "Waiting on" is read-only and "What the system did" goes.
- Build the demo panel. Remove `start_run` and `deliver_reply` from `inWords`.
- Apply the branding.
- Delete `QueuePage.tsx`, `LeadDetailPage.tsx`, `ItemsSection.tsx` and `EventList.tsx`, and settle each frontend test as the table above says.
- Make the documentation changes.
- Make the replay attempt with the three example prompts.

Done when: lead 008 runs from "Load today's leads" to an approved packet entirely in the conversation, leads 003 and 000 show their cards inline, a citation chip opens the panel, `make check` passes, and the fresh-clone rehearsal (`tools/fresh_clone.py`) passes.

## Build rules

These are the rules of "How the work runs" in `docs/plan.md`.

- **One line of work.** One branch, one milestone at a time, in the order above. A milestone is done when its "Done when" holds on the running system.
- **Vertical first.** Inside a milestone, get the thinnest path working end to end, then widen it. Do not build a layer ahead of the lead that needs it.
- **Tests.** Write a test first for behaviour with a consequence: the behaviour pinned above. Table-driven tests are preferred. Do not write tests that only assert a model, enum, table or config file rejects malformed input, that a document says what the code says, or that a constant has its value. Integration tests run against the real containers.
- **Review.** The lead reads every diff. The `reviewer` subagent reads each milestone once, at its end, and also reports what can be removed.
- **Contradictions.** Where this document is silent or disagrees with the code, the lead takes the simplest reading that keeps a lead moving safely and records it in one line in `docs/progress.md`. The lead stops for Brett only when the choice changes what an underwriter or a producer sees, or spends money.
- **Clean code.** No dead code, no unused field, setting or parameter, and no abstraction with one user. Code for a cut item is deleted, with its tests.
- **Acceptance.** `docs/acceptance.json` holds at most three checks per milestone, each a command that proves a "Done when" line, keyed `C1-A1` and `C2-A1` onward so they do not collide with the plan's `M1` to `M6`. The lead writes them at the start of the milestone.
- **Budget.** Live calls happen only where a milestone names them: the chat re-record in milestone 1 and the replay attempt in milestone 2. None runs in an uncapped loop. Each record run's token count goes in `docs/progress.md`.
