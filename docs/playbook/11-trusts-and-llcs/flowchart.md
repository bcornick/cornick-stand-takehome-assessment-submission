# Trusts & LLCs

FigJam page: **Trusts & LLCs**. Drill-down for the *Trusts & LLCs* criterion on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000
    classDef cancel fill:#fbe3cc,stroke:#e6a23c,color:#000

    ROOT{"Trusts & LLCs"}
    ROOT --> QUEST["Require Trust & LLC Questionnaire within 30 days of bind"]
    QUEST --> NOTREC["Not Received within 30 Days"]
    QUEST --> REC["Received within 30 Days"]
    NOTREC --> CANCEL["Cancel w/in UWing Period"]
    REC --> SCREEN["Screen for Unacceptable Exposures:<br/>• Income<br/>• Sales<br/>• Employees orher than household staff<br/>• Commercial Properties<br/>• Aviation<br/>• Watercraft"]
    SCREEN --> FOUND["Unacceptable Exposures Found"]
    SCREEN --> NONE["No Unacceptable Exposures"]
    FOUND --> CANCEL
    NONE --> ASSETS["• Ensure only assets owned by the Trust or LLC are covered by the policy, usually just Cov A and Cov B. Occupants of the home should have separate THO policy for their personal property. Exclude Cov C.<br/>• Change to Premises Liability Only"]

    class CANCEL cancel
```

## Reading notes

- "Cancel w/in UWing Period" is orange on the board.
- The vertical line between "Unacceptable Exposures Found" and "Cancel w/in UWing Period" looks like one two-headed arrow, but appears to be two connectors sharing a segment: the arrow from "Screen for Unacceptable Exposures" curves in and ends with the downward arrowhead into "Found", and a separate arrow runs from "Found" up into "Cancel". Read as Screen → Found → Cancel.
- "orher" is spelled that way on the board.
- "THO" is not defined on the board (plausibly a tenant homeowners policy).
