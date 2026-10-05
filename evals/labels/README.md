# Seed-42 labels

Expected results for the ten seed-42 leads, one YAML file per lead under `seed42/`, written from the registry, the playbook transcriptions, the data files under `src/uwh/rules/data/` and the provider fixture `world-42.json`, without reading the rules or skills code (architecture section 13.2). Brett signs a label by writing his name in `reviewed_by`. `excluded_edges.yaml` lists the terminal board edges the interpretation rows remove from per-page case coverage.

## A lead label

- `first_pass` is the state at the settle point, before any underwriter action. `status` is the lead status; `outcome` is one of `request_sent`, `proposed_decline`, `underwriter_card`, `quote_sent`.
- `request.asks` names the registry fields asked, field requests and follow-on questions together, in no particular order. `confirmations` are validator ids from `wording.yaml`; `catalogue_questions` are ids from `catalogue.yaml`. `kind` is `routine_request` unless a catalogue question or document request is in the message.
- `suppressed` (lead 000 only) lists the asks and confirmations a proposed decline holds back, so the answer-key grader's decline exemption count is pinned.
- `not_asked` lists every field missing on the lead that must not be asked, with the reason: `bind_only`, `fetched` (a system-owned field the stand-in provider returned), `blocked` (a lookup missing an input, or a field conditional on a blocked `protection_class`), `derived`, `condition_inactive`, `never_asked` (`opening_protection`).
- `underwriter_items` are the open items: choice ids from the section 9.7 table, `decline_notice` for a proposed decline awaiting approval, or a review cause.
- `pages` covers the seven built pages. `applies` is `yes`, `no` or `unknown` (the `applies_when` fact is missing, blocked or in an open conflict). `outcome` is `no_action`, `requirement`, `surcharge`, `exclusion`, `decline`, `choice_open` (an unanswered underwriter choice at the root) or `undecided` (a test on an unknown fact). `trace` is the board path, page number and Mermaid node id.
- `not_evaluated` lists the cut pages, and the overview's Animals criterion (I46), that apply to the lead and so carry a note.
- `effects` lists what a producer sees in the packet or plan: `type`, `text`, `deadline` where typed, `from` the board box or row.
- `underwriter_actions` scripts the actions played after the first pass; `after_actions` is the expected state afterwards, in the `first_pass` shape plus `facts` and `packet` where the scenario fills them.
- `alternatives` holds a second scripted path for the leads whose one choice can be ruled either way (003, 006); each entry has its own `underwriter_actions` and `after_actions`. `held_catalogue_questions` there names a collected catalogue question that waits for the open round to close.
- `questions` lists the points on which the sources are silent or unclear, for Brett.

Missing means JSON null; `"None"`, `false`, `0` and `"Unknown"` are present values. Values the lead carries are never asked again, whatever a page says.
