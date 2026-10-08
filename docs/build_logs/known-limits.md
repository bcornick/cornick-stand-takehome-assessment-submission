# Known limits

What is left as it is in this proof of concept, from the reviews and from `docs/build_logs/progress.md`. The README lists the ones a reviewer is most likely to meet.

- A post in flight when a run is replaced may still reach the mailbox; every commit checks its run id, so the work writes nothing else.
- A stale browser tab after a new run is refused on an item it does not know.
- Paths no seed-42 lead reaches stop with a stated `data` blocker: the KYC range validator and its identity-score reviews, and the no-contact-route item.
- Round 2 goes beyond the fixtures: the reply fixtures answer a first request, so a second round has no fixture reply.
- No pricing or rating, no live third-party data (addresses are synthetic), and reply text comes from fixtures or the paste box, not a simulator.
- The graders score each request from the ask ids stored on the intent, not from the delivered email text; a body that dropped a question would pass Asks and Forbidden asks.
- An edited draft is not checked for pricing, a decline reason or internal notes before it is sent; the underwriter approves every edited draft and sees its text.
- A chat turn that finishes after a new run has started writes its proposal card into the new run.
- Proposal-card ids restart with each run (item ids do not), so a stale tab's Apply can hit the new run's card with the same number.
- In the replay demo the assistant answers only the three example questions, each asked first in the Queue conversation on the day as first loaded; once the replies are delivered, or after another question, an example closes with "Questions need live mode". A `live` or `record` run answers any question.
- A citation proves the assistant was shown the item, not that the item supports the claim.
- Dismissing a proposal card writes outside the command layer and records no event.
- A round-2 rewrite runs inside the command's transaction, so a slow model call holds the write lock for other leads.
- The runtime does not gate a skill on its eval status; the results log is read by `make eval` and by people.
- `Reply facts` is scored on the seed-42 run beside the nine graders of the design spec.
- Stored input-token counts leave out cached input, so the budget totals undercount.
- Two reply tests and the deck-height test feed hand-made model readings to test the code after the model.
