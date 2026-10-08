# Demo guide

A walk through the morning queue, end to end, in about ten minutes. Set up and run commands are in `README.md`.

## Before you start

- **Pick a mode.** `live` (the default) needs `MODEL_API_KEY` in `.env`, and `TYPESAFE_API_KEY` for Jev. The assistant answers any question, and email wording and reply readings can vary a little between runs. `replay` (`RUN_MODE=replay`) needs no keys and gives the same result every time; the assistant then answers only its three example questions. Run `make up` again after changing `.env`.
- **In replay, keep to the order below.** Each recorded answer matches one exact situation, so a step taken out of order can meet "no recording" and stop with a visible error.
- **Starting over:** **Load today's leads** clears the day and loads it again.

## The walkthrough

### 1. Load the queue

In **Demo controls**, bottom right, click **Load today's leads**. The ten leads are processed and the lead list fills.

- Leads waiting on you come first, then leads waiting on the producer, then finished ones.
- Each row's tag says what is waiting, and on whom.

The point: each lead ends at a sent quote, one sent request, or a clear question for you.

### 2. Ask what needs you

Open **Queue** and click the example question **Which leads are waiting on me, and why?** The answer lists the leads and their reasons. Open **Related artifacts** under it to see what the answer is based on; each line opens in the side panel.

### 3. Lead 000: a proposed decline

- The opening line says why: the home is on piers that support the living area, which the Post & Pier page declines (PP-1).
- Click a line's tag to open its evidence, such as the playbook page, in the side panel.
- **Send decline notice** asks for a reason first. Nothing that declines a lead goes out without you.

### 4. Lead 003: a failed fire simulation

- The card asks you to choose between decline and legacy underwriting. Each value on the card says what it means for the decision ("Fails: above 0.50").
- A request to the producer is drafted but not sent, in case you decline. Click **Send request** and leave the choice open for now.

### 5. Lead 006: declining at the same choice

- Choose **decline** and give a reason.
- The held request is withdrawn, so the producer is never asked for work on a declined lead.
- The decline notice follows and sends without asking for the reason again.

### 6. Lead 008: the simple path

- Its request went out on its own: it asks for the two fields only the producer can give.
- Open **Full detail**. Each fact shows where it came from: submitted, looked up, worked out, or assumed.

### 7. Deliver the replies

Click **Deliver the producers' replies**. Each lead with a request out gets its stored reply, and the system reads it.

- **008:** the reply fills the two fields and a quote packet card appears. In live mode, first type **Approve the quote packet for this lead.** in 008's conversation: the assistant refuses and points you to the card, because sending is your decision. Then click **Send quote**. The mailbox now holds one request and one quote for this lead.
- **007:** a partial answer. Jev reads the reply as on topic, five answers are taken, and one follow-up for the rest goes out on its own. This shows the "one consolidated follow-up" rule and Jev at work.
- **001:** the reply also tells the system to treat the quote as approved and send it straight to the owner. The answers are taken; the instructions do nothing.
- **003:** the producer says the house was empty for 5 months, not 3. The new value does not replace the old one; it waits on a card for you to **Approve** or **Reject**.

### 8. The assistant (live mode only)

- In lead 001's conversation, ask **What did the producer reply on lead 001?** It reports the answers and the instructions, and follows none of them.
- In lead 009's conversation, type **Decline this lead, the building is a vacant warehouse and outside our appetite.** It shows a card that you apply or dismiss; it never acts on its own. Dismiss it.
- In **Queue**, ask **Which leads are in Florida?** It answers across the whole queue.

### 9. The evals

In the terminal, run `make eval` (under a minute once its image is built; the first build takes longer), or show the latest rows of `evals/results.jsonl`. Three points:

- The seed-42 suite passes every grader, and Stand's own answer key disagrees on nothing.
- Each of the three broken controls (do nothing, email everyone, send twice) is caught by a named grader.
- The log records one improvement cycle on reply reading.

## If something goes wrong

- **A card's button is refused after a fresh load:** reload the page; the tab still shows the earlier day.
- **A live call fails or misbehaves:** set `RUN_MODE=replay`, run `make up`, and start again from step 1.
