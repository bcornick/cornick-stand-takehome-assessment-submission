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

- **Orientation.** The ten leads follow section 5 of `docs/architecture.md`. Field values come from the seed-42 queue as the leadgen container serves it, so the pages show real variety. The run is a settled first pass in `replay` mode; the simulated clock stands two days after the first pass, so some leads are past the service level and some are not. A lead's age counts Monday to Friday in UTC (section 7.6).
- **Facts.** A lead lists the fields it has a value for, not all 73 registry fields. A field with no value has no fact. Section 9.4 sets the source of a provider field (`broker_tier`, `has_primary_policy_with_stand`, `replacement_cost`, `protection_class`, `kyc_score`, `p_f`, `slope_angle_deg`, `min_distance_to_neighbor_ft`, `vegetation_clearance`, `road_access`). A value the seed-42 payload carries is `submitted`, with no lookup. A field the payload leaves null is looked up: the input check runs first, so a lookup whose inputs are missing is `blocked` and leaves no fact (the `provider_called` event names the missing inputs and the triage resolution is `blocked`), and a lookup with its inputs is `fetched`. The inputs are the full address (`street_address`, `city`, `state`, `zip`) for every provider field but three: `kyc_score` needs `first_name`, `last_name` and `insured_dob`, and `broker_tier` and `has_primary_policy_with_stand` need only the lead id. Fetched values are synthetic. No fact is `assumed`: the default for `protection_class` applies only when the lookup returns `not_found`, which no seed-42 lead has. A classification is `derived`; lead 009 carries a stub `p_f`. No fact is `confirmed` and none is pending review.
- **Rule ids and board paths are display data.** The rule ids and board paths in these files (`07:LIVING`, `02:HIGH1`, `04:D_FAIL`) are illustrative values written by hand. They follow the playbook transcriptions under `docs/playbook/` where a box exists and are schematic otherwise. They are not the output of the decision graphs, and nothing checks them against the graphs. The ask lists and recipients follow section 10. Subjects, openings and the grouping and numbering of asks follow appendix A.8 and section 10.2; the wording of each ask is illustrative and is not the rendered text of any implementation.
- **Playbook pages.** Every lead lists twelve pages. Plumbing and Electrical are `not_evaluated` on every lead, each with its note (section 4.1). The other pages are `no`, `unknown` or `yes` from the lead's facts, so the fixtures hold each `applies` value and the results `decided`, `undecided` and `not_evaluated`. An open conflict makes a page undecided, so no page here declines on every branch.
- **Where the leads depart from section 5.** Section 5 names what a lead is notable for. The fixtures add what the facts imply: a blocked `kyc_score` lookup leaves Profile undecided, a missing `pool_type` leaves Pools undecided, a blocked `protection_class` lookup leaves PC 9 & 10 undecided and keeps the four fields conditional on protection class 9 or 10 out of the request. Lead 000 holds the occupancy conflict (section 2.2), so its Occupancy page is undecided; its one decline is Post & Pier, and its decline notice is round 0 because the lead has had no request. Its Profile, Pools, PC 9 & 10 and Replacement Cost pages are undecided beside it, and no request or confirmation goes out (section 9.6, precedence 1). Lead 008 carries an `unevaluated_skill` note for `read_reply`; no lead carries a `skill_fallback` note, because the one model skill with a fallback is untested, not failing.
- **Items.** `items.json` holds the decline-notice draft review of lead 000 and the question cards of leads 003 and 006. There is no pending-observation, persistent-cause or `delivery_unknown` item, because section 5 describes none.
- **Settings, skills, proposals.** `deliver_reply` is set to `review` to show a level that differs from its default. Every skill threshold is 1.0 (A.10). No skill is `failing`: a deterministic skill that failed would stop its lead with a `data` blocker (section 8), and every lead here holds a rendered message. `read_reply` is `untested`, `chat` is `unavailable`. One open command proposal approves lead 000's decline notice with the draft's payload hash; one open rule-change proposal is for row I12.
- **Event stream.** `GET /api/events/stream` answers 501 in the stand-in, as it does in the app; a client sees no live updates.
