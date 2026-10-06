# Reply labels

Expected results for the reply fixtures in `fixtures/replies/`, one YAML per fixture, written from the seed-42 labels (the asks each lead was sent), the registry, `wording.yaml`, `catalogue.yaml` and `world-42.json`, without reading the rules or skills code (architecture section 13.2). The bodies ship in the app image; these labels do not.

## A reply label

- `intent` names the request the reply answers (`first_request` is round 1). `classification` is the architecture's: `answers_all`, `answers_some`, `off_topic`, `declines_to_answer`.
- `facts` are the values that become effective facts (section 7.3 rule 2); `pending_review` the values that differ from an existing value (rule 3, or rule 6 when a confirmation is answered with a different value). Values use the registry's types and option spellings: a select answer is one of its options, dates are `YYYY-MM-DD` strings, integers are numbers, toggles are booleans.
- `confirmations` holds, per confirmation asked, `restated` (closes the conflict) or `changed` (follows rule 3). `unanswered` lists asks the reply does not answer; a follow-on whose condition the reply makes inactive is neither answered nor unanswered. `dropped` lists values the code must drop: a field not asked or a value outside its type or options.
- `state_after`: `round_closed`, the `underwriter_review` the reply raises (or null), and `next`: `quote_packet_waiting`, `request_round_2`, `underwriter_card` or `declined_pending`.
- `instruction_ignored` quotes an instruction aimed at the system, from which no command results. `notes` records each point where the sources are silent and a reading was chosen.

| Lead | Kind | Classification |
|---|---|---|
| 009 | full, one ask | answers_all |
| 004 | full with a restated confirmation | answers_all |
| 007 | partial | answers_some |
| 003 | contradicting (confirmation answered with a different number) | answers_all |
| 001 | instruction-bearing | answers_all |
| held/005 | values in prose needing normalisation; a changed confirmation | answers_all |
| held/006 | off-topic question back | off_topic |
| held/002 | withdrawal | declines_to_answer |

The three under `held/` (bodies in `fixtures/replies/held/`) are kept from the `read_reply` implementer until the eval run; the improvement cycle is run on one that fails (section 13.2).
