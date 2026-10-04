# Critique of `docs/architecture.md`

Independent review for the build team. Citations use `file:line`. `arch` means `docs/architecture.md`. Claims about the generator were checked by running Stand's unmodified `leadgen/generator.py` from a scratch copy with seed 42, and with seeds 1 to 50 and 0 to 1999 for sweep claims. A claim that could not be checked is marked "unverified".

## Verdict

The rules-first design is sound and most harness facts in section 2.2 are correct against the code. The document fails on three counts that matter more than any single rule. It carries roughly ten times the brief's 5 to 6 hour budget (`docs/brief/agentic_uw_takehome.md:13`) and names no cut line. It calls itself the single authority for the build (arch:3) yet leaves out every contract that two coding agents must share: event names, table columns, REST routes, graph YAML schema. And it leaves the ordering between an underwriter question and a producer request undefined, which changes the first-pass state of three of the ten seed-42 leads. The eval design grades the system against labels written from the same interpretation table, while Stand's own answer key is demoted to a side count. The interpretation table hides at least five eligibility decisions behind the "assumed" tag and misreads one registry field. Fix the three blockers before stage 1; fold the major findings into section 9.7 and section 13 before the stage 3 labels are written.

Counts: 3 blockers, 14 majors, 11 minors.

## Verified facts used below

Seed 42, count 10, mixed difficulty, supplied config:

| Lead | Source | Tier | Archetypes | Missing always-required producer fields | Notable values |
|---|---|---|---|---|---|
| 000 | direct_web | hard | occupancy_conflict, post_and_pier | 23, plus `deck_height_ft` | piers support living area; Primary with 8 months unoccupied; all five address fields null |
| 001 | agent_portal | medium | none | 13 | `street_address` null; `water_heater_type` null |
| 002 | broker_email | medium | profile_kyc | 6 | KYC 8; `pool_security` null with `pool_type` "None" |
| 003 | direct_web | hard | wildfire_severe, occupancy_conflict | 13 | `p_f` 0.79; Primary with 3 months unoccupied; city and zip null |
| 004 | broker_email | medium | none | 5 | residents 0 (conflict); animals |
| 005 | direct_web | hard | profile_kyc | 14 | KYC 6; residents 0 (conflict); `pool_type` null |
| 006 | broker_email | hard | wildfire_severe | 19 | `p_f` 0.89; state, zip, last name null |
| 007 | agent_portal | medium | profile_kyc | 8 | KYC 9 |
| 008 | broker_email | easy | none | 2 | `property_purchase_date`, `electrical_panel_brand` |
| 009 | agent_portal | easy | none | 1 | `acreage` |

- No seed-42 lead is complete. Zero quotes can go out on the first pass.
- The guarantee pass fired on 0 of 2,000 seeds. It cannot fire for ten mixed leads: four hard leads each draw one or two archetypes (`generator.py:177-178`), which meets the guarantee of four (`generator_config.yaml:10`). arch:31 is correct.
- Seeds 1 to 50 produce 417 archetype instances covering all ten archetypes (fewest: `plumbing_water_heater` 23, `pool_hazard` 25).
- Registry counts 73 / 52 / 18 / 3, six `requiredWhen` strings and six conditional fields without one all match arch:22 and arch:38.
- SQLite row ids keep increasing after `DELETE` on an `AUTOINCREMENT` table (`store.py:30`, `store.py:113`). arch:34 is correct.

## Blockers

### C01. The design has no cut line and exceeds the brief's budget by an order of magnitude

- **Severity:** blocker
- **Evidence:** The brief sets 5 to 6 hours and says the decision of what to cut is evaluated (`agentic_uw_takehome.md:13`), and asks for the core loop over exhaustive rule coverage (`agentic_uw_takehome.md:41-42`). The architecture commits to: an event log, a two-layer fact ledger with staleness, a command layer with autonomy levels, intent-based sending with reconciliation, live and replay modes (arch:156-234); seven skills with digest-based status (arch:236-264); 12 YAML graphs, an interpreter with path exploration, 47 interpretation rows (arch:355-455); a React surface with five panes, server-sent events, chat and MCP (arch:509-522); a rule-change flow with dry run (arch:527); 15 graders, 7 controls, a 50-seed sweep and a committed results log (arch:530-587); an optional Jev adapter (arch:153, arch:503). Section 4 lists non-goals, but nothing in sections 6 to 14 is ranked. `docs/plan.md` is referenced by `README.md` and arch:146 and is absent from `docs/`, so the stages cited at arch:74, arch:405 and arch:600 are undefined in the authority document.
- **Why it matters:** Coding agents remove the typing cost, not the integration and verification cost. An unfinished wide system demos worse than a finished narrow one, and reviewers will ask what was cut.
- **Recommended change:** Add a section "Build tiers" with three tiers and make every later section name its tier.
  - Tier 0 (must demo): compose, queue ingest, triage, derive and fetch, the graphs that seed 42 touches (Profile, Occupancy, Fire Simulation, Roof, Siding, Post & Pier), ask plan, one rendered email, send with intent, reply paste with `read_reply`, quote packet with approval, queue and detail panes, seed-42 labels, the graders on asks, forbidden asks, coverage and send safety, and three controls.
  - Tier 1: remaining graphs, MCP read tools plus `propose_command`, the 50-seed sweep on invariants, emergency stop, skill status page.
  - Tier 2 (cut first, in this order): Jev adapter, replay mode, the rule-change dry-run flow, chat panel, server-sent events (poll instead), PC 9 & 10 full encoding (42 of roughly 100 outcome nodes on the board, none reachable on seed 42).

### C02. The shared contracts a coding agent needs are absent

- **Severity:** blocker
- **Evidence:** arch:3 makes this document the single authority. It does not define:
  1. Event types. arch:171 lists row columns only. Graders are "plain functions over the mailbox, event log and fact ledger" (arch:547), so grader authors and runtime authors must agree on event names and payloads.
  2. Table columns for events, observations, effective facts, intents, approvals, blockers (arch:112, arch:173-185).
  3. REST routes. Only `POST /api/replies` (arch:486) and `/mcp` (arch:522) are named. The React build and the FastAPI build have no shared route list, and the app's host port is never stated.
  4. The graph YAML schema. Node kinds and branch semantics are described in prose (arch:359-374); no example file, no band syntax, no `applies_when` grammar.
  5. `catalogue.yaml` content: ids, wording, answer type for each producer question (arch:364, arch:472).
  6. Command payloads (arch:195-207) and the status transition table for `received`, `triaged`, `in_progress`, `quote_sent`, `declined` (arch:162).
  7. Hash inputs and canonical form for "lead revision", "action-plan hash", "ruleset hash", "payload hash" (arch:211, arch:218).
  8. The skill digest: which files count as "implementation" (arch:251). A change to `rules/data/*.yaml` changes `evaluate_playbook` behaviour without touching its folder.
  9. The fixed email text: subject, from address, opening, and the per-field question wording for 61 producer-editable fields (arch:472-474).
  10. The `read_reply` output schema, length cap, model id and prompt (arch:488-501).
- **Recommended change:** Add an appendix "Contracts" with: the event type enum and one payload schema each; SQL DDL for the six tables; a route table; one complete graph file (Post & Pier is the smallest: 7 outcomes, 2 band sets); the catalogue list; the Pydantic models for commands, asks, intents and `read_reply` output. Roughly 150 lines. Without it, parallel agents will produce incompatible halves.

### C03. The order between an underwriter question and a producer request is undefined, and section 5 disagrees with section 9.6

- **Severity:** blocker
- **Evidence:** arch:392-397 suppresses requests only for a decline that follows from confirmed facts. arch:382 says effects under an unanswered `underwriter_choice` are "possible, not committed". By those rules lead 006 (no conflict, 19 missing always-required producer fields) sends a routine request automatically (arch:198) while its fire-simulation question is open. arch:84 lists only "Underwriter choice on the failed fire simulation" for 006. Lead 003 has a conflict confirmation, so its message is sensitive and waits for review (arch:199) alongside the question: two underwriter items on one lead. The document also does not say whether a producer catalogue question under an unanswered underwriter choice (I17, willingness to mitigate, arch:425) is asked.
- **Why it matters:** The answer sets the mailbox state Stand sees for leads 003 and 006 and the labels Brett signs. Stand's archetype for both leads expects a producer ask for roof material (`archetypes.py:67`). Sending a 19 to 24 question email on a lead the underwriter may decline one click later is also a product decision the document should own.
- **Recommended change:** State one rule in section 9.6 and apply it to section 5. Suggested: registry asks go out regardless of open underwriter choices unless a decline is committed; catalogue questions and document requests that sit under an unanswered choice are held; the lead shows one combined underwriter card. Then rewrite rows 003 and 006 at arch:81 and arch:84 to say which message goes out and at which autonomy level.

## Major findings

### C04. The eval grades the system against its own reading; Stand's answer key is underused

- **Severity:** major
- **Evidence:** Labels come from "the playbook transcriptions, registry and interpretation table" (arch:543), the same three inputs the rules core is built from. The independence is from `src/uwh/rules/` code only. A wrong row in section 9.7 or a wrong arrow in a transcription passes both sides. The labelling function (arch:538) is a second implementation of triage, which arch:617 rejects as an approach for the graphs. Per-outcome cases number roughly 100 plus boundaries (arch:539); only the ten lead labels carry a human signature (arch:543). Stand's debug key is "a cross-check; disagreements are counted and reported separately" (arch:538) and the document lists three systematic ways the key differs (arch:33), so a non-zero disagreement count is always expected and can never fail a run.
- **Recommended change:** Turn the key into a hard grader in the eval container. For every debug touch: `missing_required` on a producer field must appear as an ask unless the lead is a committed decline; `missing_bind_only`, `missing_system_owned` and `missing_derived` must never appear as an ask; `conflict` must produce a confirmation or an underwriter item. These match the behaviours Stand's README states (`sim-harness/README.md:90-104`). Enumerate the three allowed disagreement classes from arch:33 and assert the residual is zero. Run this on seeds 1 to 50; the first pass uses no model, so it costs nothing. Sample 15 to 20 of the per-outcome cases for a human check and record which ones.

### C05. The first pass makes zero model calls; the document does not defend that to an agent-runtime audience

- **Severity:** major (review risk)
- **Evidence:** Models are confined to reply extraction, reply classification and chat (arch:57). The harness has no reply endpoint (arch:34) and the design has no reply simulator (arch:64). A reviewer who runs the queue and does not paste a reply or open the chat sees a system in which the supplied API key is never used. The brief asks to "leverage agents and LLMs" and to show "what's possible with agents" (`agentic_uw_takehome.md:7`, `:41`). Section 17 gives one line to the rejected agent-driven alternative (arch:614).
- **Recommended change:** Keep the design; strengthen the case and the demo. (a) Add a "deliver fixture replies" control so a default run exercises `read_reply` on several leads, not only lead 008. (b) Put one measured comparison in the results log: the same ten leads through a tool-calling model for field triage, scored by the forbidden-asks and asks graders, to show why the decision path is code. (c) State in section 8 what makes this a harness: a skill added with a manifest, cases and a threshold is dispatched and gated with no runtime change. Reviewers who own a runtime will test that claim by asking how a second vertical plugs in; section 7 says the runtime holds no insurance vocabulary (arch:158) while the command classes are named `send_quote_packet` and `send_decline_notice` (arch:200-201).

### C06. The provider fixture exists only for captured seeds and replays generator internals

- **Severity:** major
- **Evidence:** `capture_world.py` records `_base_lead` output per seed (arch:321) and the provider returns the clean base value (arch:327-331). `generator_config.yaml:2` invites interviewers to re-tune difficulty; a changed weight changes the seed-42 queue while lead ids stay `LEAD-00000042-000` to `-009` (`generator.py:293`). The document does not say what a provider returns for a lead outside the fixture or for a lead whose content differs from the captured one. "Start morning run" hard-codes `seed=42` (arch:593). The found versus `not_found` split for `kyc_score` and `protection_class` (arch:329-330) depends on whether an archetype or the perturbation pass nulled the field, which is answer-key information reached through the wrapper instead of the debug endpoint.
- **Recommended change:** Store a fingerprint of each captured lead's submitted fields in the fixture and verify it at lookup. On a miss or mismatch, fall back to a deterministic synthetic value seeded by lead id, marked `is_stub` and shown as such. Say plainly in section 9.4 that the fixture replays pre-perturbation generator state and why (replacement cost must stay consistent with Coverage A). Read the seed from the environment.

### C07. Five interpretation rows make eligibility decisions under the "A" tag

- **Severity:** major
- **Evidence and change, per row:**
  - **I12** (arch:420): the board gives no criterion for a failed simulation (`04-fire-simulation/flowchart.md:72-76`). The row sets fail at `p_f` above 0.50. I16 states "no number is invented" for slope (arch:424); I12 invents one. Generated values are 0.02 to 0.20 clean and 0.55 to 0.90 under the archetype (`generator.py:151`, `archetypes.py:71`), so any threshold from 0.21 to 0.54 scores identically and the eval cannot tell them apart. Keep 0.50, mark the row as the first question for Stand, and add hand cases at 0.21 and 0.54 that record the dependence.
  - **I07** (arch:415): 2 months is ruled "over 60 days", which is a decline on every path (`03-occupancy/flowchart.md:41-45`). Two months is 59 to 62 days. Make exactly 2 months an underwriter choice.
  - **I21** (arch:429): Vinyl, Aluminum / Steel and Other take "no action". The board has two branches, Non-combustible and Wood Shake or Shingle (`06-siding/flowchart.md:12-13`); the generator classes those three materials C (`generator.py:42-46`). Add an advisory for class C materials or make it an underwriter choice.
  - **I28** (arch:436): the board names no brands (`09-electrical-systems/flowchart.md:20`). The row lists five; the path ends in decline for a non-Tier-1 broker (`:42`). Only Federal Pacific has support in Stand's code (`archetypes.py:39`). Mark the other four as the submission's assumption in the rationale and list the row for Stand.
  - **I43** (arch:451): "Require Dry Hydrant" and "Require Retrofit" are encoded as terminal (`13-protection-class-9-and-10/flowchart.md:160-162`, `:246`). A home with no dry hydrant then skips three decline checks that a better-equipped home faces: paved roads, limited access, response over 30 minutes (`:164-172`). Encode the requirement and continue, or make it an underwriter choice.
- **Also:** arch:405 has Brett review every row. Add a column "direction" (stricter or more lenient than the alternative reading) so the review can go straight to the lenient rows.

### C08. I33 misreads the registry: the gated-community field already covers multi-acre

- **Severity:** major
- **Evidence:** `is_gated_community` is labelled "In gated community or multi-acre property" (`field_registry.json:59`). I33 derives multi-acre from `acreage` of 2 or more (arch:441). The clean generator sets the toggle to false and draws acreage up to 2.5 (`generator.py:110-111`), so a lead can carry toggle false and acreage 2.3. The document does not say how the two combine; taking either as sufficient overrides the producer's answer and moves the outcome from "Require Secured Cover" to "Accept w/ Recommendation" (`10-swimming-pools/flowchart.md:18-21`).
- **Recommended change:** Use the toggle alone. Treat toggle false with acreage of 2 or more as a confirmation question, or drop I33.

### C09. Gaps on the board with no interpretation row

- **Severity:** major
- **Evidence:**
  1. Pools: "Unfenced / Uncovered" routes through the gated check, while "Fenced ... = No" routes straight to "Require Secured Cover" (`10-swimming-pools/flowchart.md:16-23`). An unfenced pool in a gated community matches both. A `one_of` loader check (arch:372) will reject this graph or the encoder will pick silently.
  2. Pools: `pool_security` "None" on a lead that has a pool (`field_registry.json:56`).
  3. PC 9 & 10: `fire_dept_response_time` "Unknown" (`field_registry.json:91`); `road_access` "Unknown" (I44 covers Single Access Point only, arch:452); Branch A at exactly 7,500 square feet (I39 covers the three-band blocks only, arch:447; `13-.../flowchart.md:67-69`); `interior_sprinklers` "Interior Sprinklers" without central monitoring.
  4. Roof: composition shingles older than 20 years sit in neither material list (`05-roof-class/flowchart.md:32-33`).
  5. Occupancy: `dwelling_use_type` "Tenant" or "Mixed" with `is_rental` "No" reaches neither the Rentals branch (I06, arch:414) nor a validator (arch:348-350 omit "Mixed").
  6. Trusts & LLCs: no registry field identifies an LLC owner.
  7. Fire Simulation: "Determine preliminary mitigation plan to discuss with broker" has no effect type (`04-fire-simulation/flowchart.md:36`).
  8. Occupancy: modifications apply "for duration of non-occupancy" (`03-occupancy/flowchart.md:44`); the deadline enum has no such value (arch:380).
- **Recommended change:** Add one row each. Items 1 and 3 need rows before the graphs are encoded because the loader checks at arch:399 depend on them.

### C10. Conflict validators are fitted to the generator's injector list

- **Severity:** major
- **Evidence:** The validators at arch:344-350 map one to one onto `CONFLICT_INJECTORS` (`generator.py:188-199`) and the three `occupancy_conflict` variants (`archetypes.py:96-106`). Thresholds sit exactly between injected and legitimate values: amps below 60 separates the injected 30 from the archetype's 60 or 100 (`archetypes.py:42`); months of 3 or more matches the archetype's range of 3 to 9 (`archetypes.py:100`). The mismatch with I06 produces an inversion: Primary with 2 months unoccupied is a confirmed fact and a committed decline (I07), while 3 months is a conflict and gets a confirmation question. The year anomaly at arch:604 is detectable (`roof_replacement_year` before `year_built`) and is left out because the generator does not treat it as a conflict.
- **Why it matters:** The escalation and asks graders will score these validators perfectly on generated data and say nothing about conflicts the generator does not inject. Reviewers who wrote the generator will recognise the list.
- **Recommended change:** State the source of each threshold. Set the occupancy validator to 1 month or more on a Primary home so it agrees with I06. Add the roof-before-build validator. Add two hand cases with conflicts absent from the generator (for example `effective_date` before the reference date, `water_heater_type` Tankless with a heater age).

### C11. The unknown-value path exploration is the most fragile component and mostly redundant

- **Severity:** major
- **Evidence:** arch:384-390 follows every child at an unknown test, keeps shared assumptions per path, compares plans across paths, and caps at 2,000 paths per graph. arch:396 says the registry decides what is collected, so the "paths give different plans" result (arch:387) changes nothing for registry fields. The exploration earns its place in two cases only: every path declines (arch:386), and deciding which catalogue questions are reachable. Plan equality is undefined when paths contain underwriter choices or ladders. PC 9 & 10 has about 12 unknown inputs on a first pass.
- **Recommended change:** Replace it with three-valued evaluation: each node returns decided, undecided, or decline-on-all-branches; collect catalogue questions only from nodes whose parents are decided; propose a decline only when the root resolves to decline. This removes the cap, the path-count test and the plan comparison. Keep the Post & Pier case (deck over 12 feet declines whatever `post_pier_supports_living_area` is) as the acceptance test.

### C12. Skill status by digest is brittle at review time and `untested` has no dispatch rule

- **Severity:** major
- **Evidence:** Status comes from the latest results row whose digest matches (arch:251). Any edit after the last eval run, including a prompt typo fix, shows every affected skill as `untested` in the demo. arch:252 defines dispatch for `failing` only. `evals/results.jsonl` must be readable by the app while "labels and expected results stay out of the app image" (arch:543); the mount is unspecified. Model-skill results depend on the model id, which the document never pins and which Stand's key may resolve differently.
- **Recommended change:** Define dispatch for all four statuses (suggest: `untested` model skills run and the lead shows "unevaluated skill"; `untested` never falls back silently). Include the model id in the digest. Add a release check that fails when any skill is `untested` at the tagged commit. State the mount for `results.jsonl`.

### C13. Half the queue waits on the underwriter after the first pass and the eval cannot see over-escalation

- **Severity:** major
- **Evidence:** By section 5 and the command table, seed 42 ends its first pass with 5 automatic emails (001, 002, 007, 008, 009), 5 leads waiting on the underwriter (000, 003, 004, 005, 006) and 0 quotes. Leads 004 and 005 wait only because a code-rendered, neutrally worded confirmation is classed sensitive (arch:199, arch:464, arch:474). A wildfire lead can raise up to four separate underwriter choices (I13, I14, I15, I16) and questions are "never batched" (arch:513). The brief names "did it avoid unnecessary escalation" as an eval target (`agentic_uw_takehome.md:81`) and asks for an experience that does not need babysitting (`:9`). Escalation precision (arch:558) is measured against labels that encode the same policy, so it reports 100% by construction; the "send everything to the underwriter" control (arch:579) proves the grader fires, not that the policy is tight.
- **Recommended change:** Make code-rendered confirmations `auto` by default and keep review for edited drafts and document requests; that moves 004 and 005 to automatic and the first pass to 7 emails and 3 underwriter items. Present the fire-simulation choices as one card per lead with the legacy checklist values. Report the escalation rate as a headline number with the reason per lead, and state the target.

### C14. The eval topology and fault-injection seam are unspecified

- **Severity:** major
- **Evidence:** arch:131 lists four compose services. arch:534 requires dedicated leadgen and mailbox instances for evals and arch:232 gives replay its own mailbox, which implies up to three mailbox instances. The document does not say whether the eval runner drives the app over HTTP or imports it, how the runner reads the app's SQLite file, or how it injects "crash after mailbox acceptance", "query-empty-while-in-flight" (arch:559) and provider `unavailable` (arch:337).
- **Recommended change:** Specify: the eval imports the app in process with its own database path and points at `leadgen-eval` and `mailbox-eval` services under a compose profile; faults are injected through one documented transport hook on the mailbox and provider clients. List the services, profiles and volumes in section 14.

### C15. Packaging choices work against Stand's reviewers and the "any OS" requirement

- **Severity:** major
- **Evidence:** (a) `DEBUG` is hard-coded to false on leadgen (arch:321, arch:591). The debug endpoint is the interviewer's answer key (`sim-harness/README.md:79`, `:58`); hard-coding removes it from the people it was built for. (b) arch:591 replaces Stand's port mapping without stating the chosen ports; Stand's documented URLs are 8081 and 8025 (`sim-harness/README.md:26`). (c) arch:595 states Windows as untested while arch:50 records the requirement to run on any device and operating system. (d) The volume type for the SQLite files is unstated; Stand's compose uses a bind mount (`docker-compose.yml:13`), and SQLite locking on bind mounts under Docker Desktop is a known source of faults (unverified on the reviewers' machines).
- **Recommended change:** Pass `DEBUG: "${DEBUG:-false}"` through and rely on the client having no debug method. Keep host ports 8081 and 8025 for the interactive instances and state the app port. Use named volumes for all SQLite files. Run the compose file once on Windows with WSL2 and once on an amd64 Linux host and record both in the README.

### C16. A reply that confirms a conflicting value has no rule

- **Severity:** major
- **Evidence:** The source-authority rules cover a reply filling a missing field and a reply that differs from a submitted value (arch:180-181). A confirmation asks about a present value (arch:342). If the producer answers "yes, 8 months is correct" on lead 000 or "0 residents, the home is empty" on lead 004, the reply equals the submitted value. No rule closes the conflict, marks the fact confirmed (arch:394), or says which field of a two-field conflict the answer settles.
- **Recommended change:** Add rule 6 to section 7.3: a reply that restates a conflicting value closes the conflict, records a reply observation as evidence, and marks the fact confirmed; a reply that changes either field of the pair follows rule 3. Add one reply fixture for each case.

### C17. The Unknown Class roof branch and the 20-year rule are unreachable under I20

- **Severity:** major
- **Evidence:** I20 takes the class from the generator's map when the material is present and applies roof age only on the Unknown Class branch (arch:428). The class is unknown only while `roof_material` is missing, and the Unknown Class branch then tests the material (`05-roof-class/flowchart.md:32-40`), which is the missing field. After the producer supplies the material the class derives and the branch is left. The board's "installed or replaced within the past 20 years" condition therefore never applies. arch:275 gives a test fixture's map authority over a playbook rule. Clean generated roofs are replaced in 2010 to 2023 (`generator.py:122`), so no generated lead exposes the difference.
- **Recommended change:** Keep the map for derivation (the registry's `derivedFrom` supports it, `field_registry.json:99`), and add an advisory for composition roofs older than 20 years with `p_f` above 0.15. Add a hand case for a 2001 asphalt roof at `p_f` 0.6 and record the ruling as a question for Stand.

## Minor findings

### C18. The model API claim is unverified and no model id is pinned

- **Severity:** minor
- **Evidence:** arch:153 states that current Claude models reject forced `tool_choice` and that `messages.parse()` is the structured-output call. Unverified against current SDK documentation in this review. No model id, token cap or timeout appears anywhere.
- **Recommended change:** Check both claims against the SDK documentation at stage 1, pin a model id in `.env.example`, and record the SDK version in the lockfile.

### C19. Cut the Jev adapter

- **Severity:** minor
- **Evidence:** Jev access and output shape are unverified (arch:599). Stand's run has no key (arch:503). The cascade adds a confidence threshold while the surface shows no confidence (arch:518). Its only output for reviewers is recorded rows from a path they cannot run.
- **Recommended change:** Remove it from sections 6.2, 8 and 10.4. Mention it in the hit list.

### C20. Small inaccuracies and dangling references in the document

- **Severity:** minor
- **Evidence:** (a) arch:32 counts three `profile_kyc` and two `wildfire_severe` leads but not that `occupancy_conflict` is on two leads (000 and 003). (b) arch:3 says critique findings are dispositioned in section 13; section 13 is Evals and the dispositions section is 16 (arch:606). (c) arch:146 lists `plan` under `docs/`; the file is absent. (d) arch:131 names four services and arch:534 needs more.
- **Recommended change:** Correct each line.

### C21. The two-business-day promise has no source in the repo

- **Severity:** minor
- **Evidence:** arch:511 ages leads against a "two-business-day promise". The phrase appears in neither the brief, the playbook nor the harness. Unverified.
- **Recommended change:** Cite the source or label it an assumed service level in the interface.

### C22. The knob-and-tube default asks more than the board requires and can ask about assumed wiring

- **Severity:** minor
- **Evidence:** arch:316 assumes true below 1950 and asks at 1950 or later. The board note reads as inferring the answer either way from the 1950 cut-off (`09-electrical-systems/flowchart.md:48`). With an assumed true, the graph proceeds to the catalogue questions on isolated versus whole-house wiring (I27, arch:435), so the email asks about the extent of wiring nobody reported.
- **Recommended change:** When the value is assumed, ask one combined question: whether knob-and-tube is present and, if so, where. State the 1950-or-later choice as a row in section 9.7.

### C23. The answer-key grader checks the app's own record

- **Severity:** minor
- **Evidence:** "The app makes no request to the debug endpoint" (arch:562). Leadgen stores no request log (`leadgen/main.py`), so the grader can only read what the app logs about itself.
- **Recommended change:** Replace it with a static test that the leadgen client module contains no `/debug` path, plus a transport-level recorder in the eval run.

### C24. `contacts.yaml` is keyed per lead

- **Severity:** minor
- **Evidence:** arch:480 sends to "the directory's producer address for that lead". Lead ids exist only for generated seeds; the 50-seed sweep has no directory entries.
- **Recommended change:** Key the mock directory by `source`, one address each for `agent_portal` and `broker_email`.

### C25. Crash recovery for sends is a scenario without a mechanism

- **Severity:** minor
- **Evidence:** arch:94 and arch:559 require no second email after a crash between send and record. arch:218-221 covers an ambiguous result within a live call. No startup step reconciles intents that lack a mailbox id.
- **Recommended change:** Add step 5 to section 7.5: at startup, reconcile every intent without a mailbox id before any dispatch.

### C26. Two brief deliverables have no home in the document

- **Severity:** minor
- **Evidence:** The brief asks for a prioritised hit list of next skills (`agentic_uw_takehome.md:82`) and for the third-party sources that would be wired in versus stubbed (`:36`). Section 8 lists built skills only; section 9.4 names no real provider behind any stub.
- **Recommended change:** Add a column to the provider table naming the real source class for each field, and a short hit-list section or a pointer to the README section that holds it.

### C27. The three-state objective departs from the brief's two states without saying so

- **Severity:** minor
- **Evidence:** The brief defines two clean end states (`agentic_uw_takehome.md:23-26`). arch:9-11 adds "waits on a named human decision". Lead 000 gets no email on the first pass although Stand's archetype expects a producer ask for deck height (`archetypes.py:129`).
- **Recommended change:** State the departure and its reason in section 1: a lead whose confirmed facts decline on every path should not cost the producer 24 questions. Use lead 000 as the worked example.

### C28. Lead-level details a builder will guess

- **Severity:** minor
- **Evidence:** "Full address" (arch:328-331) is not defined as a field set. The zero-residents validator (arch:346) does not say which field marks owner-occupied or what happens when that field is null (lead 001 has `dwelling_type` null). The bounded pool size (arch:164) and the reply length cap (arch:501) have no values. The ask order within a section (arch:474) is unstated, which the both-directions grader does not need but snapshot tests will.
- **Recommended change:** State each value in the contracts appendix from C02.

## Review risk: what a 45-minute panel will probe

1. "Where is the agent?" See C05. The weakest point of the design under this audience.
2. "What did you cut?" See C01. The current answer is a non-goals list beside a very wide build.
3. "How do you know the eval is right?" See C04 and C13. The honest answer today is that labels and code share one reading. The debug-key grader in C04 is the strongest available reply because Stand wrote that key.
4. "Show a skill failing and the fallback firing." arch:252 promises it; no control in section 13.4 forces `read_reply` to `failing`. Add one.
5. "Can an MCP client or the chat cause a send?" The proposal-only rule (arch:209) is strong. The Policy grader (arch:561) checks the emergency stop on every entry path; add a control where an MCP client submits `approve` directly and the command layer refuses.
6. "Why does lead 004 need me?" See C13.
7. "Where did protection class 4 on lead 004 come from? The generator nulled it." See C06.

## What the architecture gets right

Do not relitigate these.

- Rules in code and data, with the model kept to language reading (arch:57). The playbook is threshold bands; a rule trace per decision is worth more than model flexibility here.
- The harness facts in section 2.2. Every one checked against the code holds, apart from the count in C20(a).
- Intent-before-send with reconciliation through mailbox metadata, and the narrow promise of no automatic resend (arch:216-223). It matches what the mailbox can support (`mailbox/main.py:46-52`, `store.py:44-54`).
- Approval bound to a frozen artifact with a recheck at dispatch (arch:211).
- Actor identity from the transport, proposal-only access for chat and MCP, and locked command classes (arch:191-209).
- Emails rendered by code from a typed ask plan, with ask ids in the intent so graders match both directions (arch:472-474).
- The registry-first triage rules: null handling, the three-result condition parser, follow-on questions for unknown conditions, never asking for system-owned or bind-only fields (arch:288-294). These match Stand's stated triage rule (`field_registry.json:14-19`).
- The interpretation table as a first-class, reviewable artifact with kinds A, P, U and N. The concept is right; the findings above concern individual rows.
- Controls that prove each grader can fail (arch:573-583), and critical errors that fail a run outright (arch:567).
- Untrusted reply text with verbatim span checks before any fact is accepted (arch:495, arch:501).
- Running Stand's services from their own Dockerfiles with code unmodified (arch:591).
