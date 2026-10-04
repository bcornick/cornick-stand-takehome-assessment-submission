# Replacement Cost

FigJam page: **Replacement Cost**. Drill-down for the *Replacement Cost* criterion on the Decision Points page. RCE = replacement cost estimate.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Replacement Cost"}
    ROOT --> BELOW["Submitted Below RCE"]
    ROOT --> AT["Submitted at Calculated RCE"]
    ROOT --> ABOVE["Submitted Above RCE"]

    BELOW --> BELOW_R["• Quote as Submitted<br/>• Advise broker we will inspect after binding and adjust coverage to align with determined Replacement Cost"]
    AT --> AT_R["Quote as Submitted"]

    ABOVE --> WITHIN150["Submitted within 150% of RCE"]
    ABOVE --> OVER150["Submitted at more than 150% of RCE"]
    WITHIN150 --> WITHIN150_R["Quote as Submitted Unless we have reason to suspect fraud, in which case we should not insure at all"]
    OVER150 --> DOCS["Broker Supplies Documentation, e.g Current Dec Page"]
    DOCS -->|Yes| DOCS_Y["• Quote as Submitted<br/>• Advise broker we will inspect after binding and offer to algin coverage with determined Replacement Cost"]
    DOCS -->|No| DOCS_N["• Quote at Calculated RCE<br/>• Advise broker we will inspect after binding and adjust coverage to align with determined Replacement Cost"]
```

## Reading notes

- "Yes"/"No" boxes on the board are folded into edge labels here.
- No boxes on this page are colour-coded; all are plain white.
- "algin" is spelled that way on the board.
- The Yes outcome's first bullet ends with a stray character on the board ("Quote as Submitted l"). The board owner confirmed it is a typo, so it is omitted here.
