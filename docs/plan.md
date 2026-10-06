# Development plan: underwriting triage harness

This is a take-home submission, reviewed in 45 minutes, for a brief that sets a 5 to 6 hour box and grades the choice of what to cut. The plan builds the smallest system that does the job well and can be read quickly. `docs/architecture.md` describes the design; where it describes something this plan lists as cut, the plan wins and the architecture text is deleted in milestone 0. `AGENTS.md` holds the working rules.

## What is built

- The ten seed-42 leads, each driven to a sent quote packet, one sent request to the producer, or a wait on the underwriter with a stated reason.
- Field triage against the registry, data resolution (derive, fetch from the stand-in providers, assume), and the conflict validators.
- The seven playbook pages a seed-42 lead reaches: Profile, Occupancy, Fire Simulation, Roof, Siding, Post & Pier, Replacement Cost.
- Request emails rendered in code, the send path with intent states and startup reconcile, and one open request per lead.
- Reply handling: the reply endpoint, the paste box, the fixture-reply control, and `read_reply` on DeepSeek.
- Quote packet and decline notice, each sent only on the underwriter's approval.
- The underwriter surface (`docs/chat-surface.md`): the lead list, each lead's conversation with its cards (approve, edit, reject, underwriter choices), the drill-down panel, the demo controls, and the chat.
- Evals through `make eval`: the seed-42 suite with its graders and Stand's answer key, the reply suite, three controls (do nothing, email everything, send twice), the results log, and one recorded improvement cycle on reply reading.
- Record and replay modes, so the demo runs from recordings.
- The Jev adapter in front of reply classification.
- `polish_message`, the conversational rewrite of request emails (§10.2).

## What is cut

Each item is listed in the README under "Cut and why". A lead that would have reached a cut playbook page carries an explicit `not_evaluated` note for it, never a silent pass.

- The five playbook pages no seed-42 lead reaches: Plumbing, Electrical, Pools, Trusts & LLCs, Protection Class 9 & 10, with their interpretation rows, catalogue questions, wording and resolution rules.
- The MCP transport. The chat calls the same functions directly.
- The 50-seed sweep.
- The rule-change flow and the model-driven triage comparison.
- The settings screens, the skills screen and the emergency stop. Autonomy levels are constants in code: a routine request sends automatically and every other message waits for approval.
- Controls and graders beyond those named under "What is built".
- The constructed packet cases and the outcome-case sample; cases are a table per page.

## How the work runs

- **One line of work.** One branch, one milestone at a time, in the order below. A milestone is done when its "done when" holds on the running system.
- **Vertical first.** Inside a milestone, get the thinnest path working end to end, then widen it. Do not build a layer ahead of the lead that needs it.
- **Tests.** Write a test first for behaviour with a consequence: a playbook outcome, a fact rule, a send-safety property, a reply reading, a command's effect, a grader. Table-driven tests are preferred. Do not write tests that only assert a model, enum, table or config file rejects malformed input, that a document says what the code says, or that a constant has its value. Integration tests run against the real containers.
- **Review.** The lead reads every diff. The `reviewer` subagent reads the milestone once, at its end, and also reports what can be removed. `/cross-review` runs once, in milestone 6.
- **Contradictions.** Where the architecture is silent or disagrees with itself, the lead takes the simplest reading that keeps a lead moving safely, records it in one line in `docs/progress.md`, and carries on. The lead stops for Brett only when the choice changes what an underwriter or a producer sees, or spends money.
- **Clean code.** No dead code, no unused field, setting or parameter, and no abstraction with one user. Code for a cut item is deleted, with its tests.
- **Acceptance.** `docs/acceptance.json` holds at most three checks per milestone, each a command that proves a "done when" line. The lead writes them at the start of the milestone.
- **Budget.** DeepSeek and TypeSafe each hold $5. Live calls happen only where a milestone names them, never in an uncapped loop. Each record run's token count goes in `docs/progress.md`.

## Milestones

### 0. Reset

- Merge the stage 3 and stage 4 branches into one branch and remove the other worktrees.
- Delete from `docs/architecture.md` every section, table row, event, route, command, setting and contract that exists only for a cut item, and state the cut list in §4. Update `AGENTS.md` and the `stage` skill to the rules above.
- Delete the code, fixtures and data for cut items, with their tests. Delete the tests the test rule excludes.
- Mark the interpretation rows of the seven built pages, and the rows that apply to every page, `reviewed_by: Brett`. Brett has reviewed them and accepts each as written, with one change: I18 puts a non-Class A roof at exactly 0.50 in the stricter band.
- Replace `docs/acceptance.json` with the checks for milestone 1.

Done when: `make check` passes; the report to Brett gives the count of tests and of lines under `src/` and `tests/` before and after; nothing under `src/` is unread by the remaining milestones.

### 1. One lead, end to end

Lead 008 goes from the posted queue to a sent quote packet through the running app: intake, triage, resolution, the pages it reaches, the ask plan, the rendered request, the send, a fixture reply read by `read_reply`, re-evaluation, the packet draft, the underwriter's approval, the send. This milestone makes the first recorded DeepSeek calls.

Done when: one integration test drives lead 008 to `quote_sent` against the real leadgen and mailbox containers; the mailbox holds exactly one request and one packet for it; the queue page shows the lead and its detail from live data.

### 2. All ten leads

The other nine leads, the seven pages in full, the conflict validators, underwriter choices, and the decline path: lead 000 is a proposed decline that waits for approval, and leads 003 and 006 each show one underwriter card.

Brett signs the ten seed-42 lead labels in this milestone.

Done when: a run leaves every lead at a sent quote, one sent request, or an underwriter wait with a reason; no lead has two open requests; Stand's answer key agrees on every seed-42 record it decides.

### 3. Evals

`make eval` with the seed-42 suite and its nine graders (Coverage, One open request, Asks, Forbidden asks, Rule trace, Packet fidelity, Send safety, Stand's key, Reply reading), the reply suite over the reply fixtures, the three controls, the cases of the two skills that have them (`evaluate_playbook` and `read_reply`), and the results log. The other skills are covered by plain unit tests. The critical errors fail the run whatever the graders say. Then one improvement cycle on reply reading: a failing case, a prompt change, the rerun, each as a row in the log.

Done when: the reference run passes every grader; each of the three controls is caught by a named grader; the results log shows the improvement cycle.

### 4. Underwriter surface

Approve, edit and reject on every item, underwriter choices with a required reason, the paste box and the fixture-reply control, the mode label, and the chat panel: read questions answered from the event log with event ids, and a directive turned into a proposal card the underwriter applies. Then the presentation pass on Brett's list.

Done when: every action an underwriter needs on the ten leads works from the browser against the running app; the chat cases pass in the eval.

### 5. Jev and the email rewrite

The Jev adapter (§10.4): ask Brett before the first live Jev call. Then `polish_message` with its two checks (§10.2).

Done when: the reply suite passes with Jev answering first and with no Jev key; a routine request in the mailbox carries the rendered question block unchanged inside a rewritten opening and closing; a rejected rewrite sends the rendered request.

### 6. Submission

Replay mode over committed recordings. The README: the run command, a one-page architecture overview, the eval loop and what to iterate on next, the skills table, and "Cut and why". A removal pass over the whole tree, then `/cross-review` once and its fixes.

Done when: a fresh clone runs with `cp .env.example .env` and one command, with and without keys; replay reproduces the demo run with no network call to a model; the reviewer and the cross-review report no blocker.
