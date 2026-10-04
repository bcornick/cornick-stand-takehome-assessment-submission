# FigJam charts: UW Agentic takehome

Agent-readable copies of the 13 pages of the FigJam board **UW Agentic takehome** (https://www.figma.com/board/cBTx4txsK4r3IJVdhFgMvu/UW-Agentic-takehome). The board is a set of homeowners underwriting decision trees for Stand Insurance.

Each page has one folder containing:

- `screenshot*.png`: image(s) of the page as drawn on the board
- `flowchart.md`: the page's flowchart as Mermaid, plus the page's side notes and reading notes (ambiguities, missing arrows, inconsistencies)

The Mermaid text is the authoritative transcription; the screenshots are for visual cross-checking.

## Pages

| # | Folder | FigJam page | What it decides |
|---|---|---|---|
| 1 | `01-decision-points` | Decision Points | Overview: lists the top-level criteria and partially expands some |
| 2 | `02-profile` | Profile | Insured's public profile / KYC score → liability exclusions or decline |
| 3 | `03-occupancy` | Occupancy | Rentals, vacant, unoccupied, for-sale properties |
| 4 | `04-fire-simulation` | Fire Simulation | Wildfire simulation result → legacy underwriting checks |
| 5 | `05-roof-class` | Roof Class | Roof fire class and P(F) band → confirmation / replacement requirements |
| 6 | `06-siding` | Siding | Siding material and P(F) band |
| 7 | `07-post-and-pier-foundations` | Post & Pier Foundations | Post-and-pier foundations and deck height |
| 8 | `08-plumbing` | Plumbing | Plumbing age and water heaters |
| 9 | `09-electrical-systems` | Electrical Systems | Knob-and-tube wiring and service panels |
| 10 | `10-swimming-pools` | Swimming Pools | Pool type, fencing, ladders, slides |
| 11 | `11-trusts-and-llcs` | Trusts & LLCs | Questionnaire and exposure screening for trust/LLC owners |
| 12 | `12-replacement-cost` | Replacement Cost | Submitted value vs replacement cost estimate (RCE) |
| 13 | `13-protection-class-9-and-10` | PC 9 & 10 | Fire protection for Protection Class 9/10: water supply, response time, staffing, home size |

Criteria named on the Decision Points page with **no** detail page: Animals, and Construction → Other attractive nuisances.

## Conventions in `flowchart.md`

- `{"…"}` diamond = the page's root criterion. `["…"]` box = any other box on the board.
- Box text is transcribed verbatim, including the board's typos (noted where they occur). Exceptions: `< =` is written `≤`, and range labels such as "P(F) > .15 < .50" are written "P(F) > .15 and < .50". A stray character the board owner confirmed as a typo (Replacement Cost) is omitted.
- Where the board uses separate "Yes" / "No" boxes, they are folded into edge labels (`Q -->|Yes| next`). A "Yes"/"No" box with no outgoing arrow is kept as a node marked "(no outcome drawn)".
- Parenthesised annotations on their own line inside a box, such as "(no outcome drawn)", are editorial and not board text.
- Colour mirrors the board: red = Decline, green = OK / quote, yellow = conditional requirement, orange = cancel. Uncoloured boxes on the board are left uncoloured.
- Where the board draws several separate boxes with the same text (e.g. several "Decline" boxes), the chart keeps them separate; where several arrows converge on one box, the chart converges on one node.
- Where board connectors overlap and the routing is ambiguous, the chart shows the routing confirmed against the board. Where the board owner confirmed an arrow the board omits (Decision Points, Siding), the arrow is drawn. Each case is described in that page's *Reading notes*.

## Gaps and inconsistencies across the board

- **The overview disagrees with the detail pages:** Occupancy, Electrical and Profile are drawn differently on Decision Points than on their own pages (details in `01-decision-points/flowchart.md`).
- **No detail page** for Animals or Other attractive nuisances.
- **Branches with no outcome:** Plumbing (tank heater newer than 10 years); PC 9 & 10 (Central Station Fire Alarm = Yes, three places).
- **Threshold gap:** Roof Class, Non-Class A, leaves P(F) = .50 unassigned.
- **PC 9 & 10** applies the Gates step to some sub-branches and not others (see that page's reading notes).
- **Undefined terms used on the board:** P(F); "UWing period" vs "first term" vs "60 days"; "Tier one broker or rounded account"; "Legacy UWing"; "7a Compliant"; KYC scale; "STR EN"; "THO".
