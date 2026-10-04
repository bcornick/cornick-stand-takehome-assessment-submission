# Post & Pier Foundations / Decks

FigJam page: **Post & Pier Foundations**. Drill-down for *Construction → Post and Pier* on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Post & Pier Foundations/ Decks"}
    ROOT --> LIVING["Foundation under any part of living area"]
    ROOT --> DECK["Support for decking only"]

    LIVING --> D1["Decline"]
    DECK --> PRE2000["Home built prior to year 2000"]
    DECK --> POST2000["Homes built year 2000 or later"]
    PRE2000 --> D1

    POST2000 --> LOW["Decks ≤ 8’ above grade"]
    POST2000 --> MID["Decks > 8’ but ≤ 12’ above grade"]
    POST2000 --> HIGH["Decks > 12’ above grade"]
    LOW --> S15["Proceed with 15% Surcharge"]
    MID --> S25["Proceed with 25% Surcharge"]
    HIGH --> D2["Decline"]

    class D1,D2 decline
```

## Notes on the page

- Text box beside the root: "If this field is missing you can try to check zillow to look at the deck construction. Otherwise we will have to follow up with the broker"

## Reading notes

- The two surcharge outcomes are uncoloured (white) on the board.
