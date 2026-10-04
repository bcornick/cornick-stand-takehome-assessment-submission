# Siding

FigJam page: **Siding**. Drill-down for *Construction → Siding* on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Siding"}
    ROOT --> NC["Non-combustible"]
    ROOT --> WOOD["Wood Shake or Shingle"]

    NC --> NC_OK["No action needed"]

    WOOD --> LO["P(F) ≤ .15"]
    WOOD --> MID["P(F) > .15 and ≤ .50"]
    WOOD --> HI["P(F) > .50"]
    LO --> LO_OK["No action needed"]
    MID --> MID_R["Require confirnation of Class A or replacement within first term"]
    HI --> HI_R["Require confirnation of Class A or replacement within UWing period"]
```

## Reading notes

- No boxes on this page are colour-coded; all are plain white.
- The board draws no arrow between "P(F) > .50" and the box directly beneath it; the connection is shown here as intended.
- "confirnation" is spelled that way on the board.
- Band labels on the board are "P(F) < = .15", "P(F) > .15 < =.50", "P(F) > .50".
