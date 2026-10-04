# Swimming Pools

FigJam page: **Swimming Pools**. Drill-down for *Construction → Swimming Pools* on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Swimming Pools"}
    ROOT --> INGROUND["Inground"]
    ROOT --> ABOVE["Above Ground"]
    ROOT --> SLIDES["Pools with Slides or Diving Boards"]

    INGROUND --> UNFENCED["Unfenced / Uncovered"]
    INGROUND --> FENCED["Fenced with Self-Locking Gate or with Safety Cover"]
    UNFENCED --> GATED["Gated Community or Multi-Acre Property"]
    UNFENCED --> NONGATED["Non-gated community<br/>Non-Multi-Acre Property"]
    GATED --> REC["Accept w/ Recommendation for Secure Cover"]
    NONGATED --> COVER["Require Secured Cover within Underwriting Period"]
    FENCED -->|Yes| OKQ["Okay to Quote"]
    FENCED -->|No| COVER

    ABOVE --> LADDER["Pull-up, Locking Ladder?"]
    LADDER -->|Yes| OKQ
    LADDER -->|No| LADDER_R["Require Suitable Ladder within UWing Period"]

    SLIDES --> LOL["Acceptable with Limitation of Liability Endorsement"]
```

## Notes on the page

- Text box beside the root: "If Missing Check google maps and zillow if you dont see anything assume no"

## Reading notes

- "Yes"/"No" boxes on the board are folded into edge labels here. On the board the "Fenced…" box and the "Pull-up, Locking Ladder?" box share one "Yes" box leading to "Okay to Quote".
- No boxes on this page are colour-coded; all are plain white.
