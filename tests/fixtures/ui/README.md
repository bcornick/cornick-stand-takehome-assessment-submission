# UI fixtures

Display data for the stand-in API (`tools/standin_api.py`) and the web unit tests. **No grader and no label author reads these files.** Values are illustrative and are not expected results: the expected first pass of each seed-42 lead is fixed by `evals/labels/`, which is written without these files.

Every file is JSON that follows a response model of `src/uwh/api/views.py`. The stand-in parses each file into its model when it starts, so a file that does not fit its model stops the server with the validation error.

| File | Response model | Route |
|---|---|---|
| `run.json` | `RunView` | `GET /api/run` |
| `leads.json` | `list[QueueRow]`, in queue order | `GET /api/leads` |
| `lead/<lead_id>.json` | `LeadDetail` | `GET /api/leads/{id}` |
| `events/<lead_id>.json` | `LeadEvents` | `GET /api/leads/{id}/events` |
| `items.json` | `list[Item]` | `GET /api/items` |
| `settings.json` | `SettingsView` | `GET /api/settings` |
| `skills.json` | `list[SkillView]` | `GET /api/skills` |
| `proposals.json` | `list[ProposalView]` | `GET /api/proposals` |

`tests/tools/test_standin_api.py` checks that the files agree with each other: the queue order, each row against its lead's detail and events, the items against the open blockers, the run's counts against the leads, the payload hashes and the plan hash.

## What the content is

- **Orientation.** The ten leads follow section 5 of `docs/architecture.md`. Field values come from the seed-42 queue as the leadgen container serves it, so the pages show real variety. The run is a settled first pass in `replay` mode; the simulated clock stands two days after the first pass, so some leads are past the service level and some are not.
- **Facts.** A lead lists the fields it has a value for, not all 73 registry fields. A field with no value has no fact. Fields the registry marks as system-owned (`p_f`, `kyc_score`, `broker_tier` and the like) are `fetched`; a classification is `derived`; `protection_class` on lead 000 is `assumed` from the registry's missing default; lead 009 carries a stub `p_f`. No fact is `confirmed` and none is pending review.
- **Rule ids and board paths are display data.** The decision graphs are not built when these files are written. The ids (`07:LIVING`, `02:HIGH1`, `04:D_FAIL`) follow the playbook transcriptions under `docs/playbook/` where a box exists and are schematic otherwise. The ask lists, recipients, subjects and message bodies follow section 10 in shape and are not the rendered text of any implementation.
- **Playbook pages.** Every lead lists twelve pages. Plumbing and Electrical are `not_evaluated` on every lead, each with its note (section 4.1). The other pages are `no`, `unknown` or `yes` from the lead's facts, so the fixtures hold each `applies` value and each `result`: `decided`, `undecided`, `declines_on_every_branch` and `not_evaluated`.
- **Where the leads depart from section 5.** Section 5 names what a lead is notable for. The fixtures add what the facts imply: a missing `kyc_score` leaves Profile undecided, a missing `pool_type` leaves Pools undecided, a missing `protection_class` leaves PC 9 & 10 undecided and keeps its four questions out of the request. Lead 000's Profile, Pools, PC 9 & 10 and Replacement Cost pages are undecided beside its two declines. Lead 008 carries an `unevaluated_skill` note for `read_reply`; no lead carries a `skill_fallback` note, because the one model skill with a fallback is untested, not failing.
- **Items.** `items.json` holds the decline-notice draft review of lead 000 and the question cards of leads 003 and 006. There is no pending-observation, persistent-cause or `delivery_unknown` item, because section 5 describes none.
- **Settings, skills, proposals.** `deliver_reply` is set to `review` to show a level that differs from its default. `read_reply` is `untested`, `chat` is `unavailable`. One open command proposal approves lead 000's decline notice with the draft's payload hash; one open rule-change proposal is for row I12.
- **Event stream.** `GET /api/events/stream` answers 501 in the stand-in, as it does in the app; a client sees no live updates.
