# Plumbing

FigJam page: **Plumbing**. Drill-down for *Construction → Plumbing* on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Plumbing"}
    DECLINE["Decline"]
    class DECLINE decline

    ROOT --> GEN["General Plumbing"]
    ROOT --> WH["Water Heaters"]

    %% General plumbing
    GEN --> OLD30["Older than 30 years"]
    GEN --> NEW30["Newer than 30 years"]
    NEW30 --> OK_GEN["Okay to Quote"]
    OLD30 --> TIER_A["Tier one broker or rounded account?"]
    TIER_A -->|No| DECLINE
    TIER_A -->|Yes| INSP_A["Require Plumbing Inspection within First Term"]

    %% Water heaters
    WH --> TANK["Tank Heaters"]
    WH --> TANKLESS["Tankless"]
    TANKLESS --> OK_TL["Okay to Quote"]
    TANK --> OLD10["Older than 10 years"]
    TANK --> NEW10["Newer than 10 years<br/>(no outcome drawn)"]
    OLD10 --> FIN["In or Above Finished Space"]
    OLD10 --> UNFIN["In Unfinished Space"]
    UNFIN --> INSP_U["Require Inspection within First Term"]
    FIN --> TIER_B["Tier one broker or rounded account?"]
    TIER_B -->|No| DECLINE
    TIER_B -->|Yes| INSP_B["Require Inspection within First Term"]

    class OK_GEN,OK_TL ok
```

## Reading notes

- "Yes"/"No" boxes on the board are folded into edge labels here.
- "Newer than 10 years" (tank heaters) has no outgoing arrow on the board.
- The inspection requirements are uncoloured (white) on the board.
- "Tier one broker or rounded account" is not defined on the board.
