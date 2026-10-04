# Occupancy

FigJam page: **Occupancy**. Drill-down for the *Occupancy* criterion on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Occupancy"}
    DECLINE["Decline"]
    class DECLINE decline

    ROOT --> RENT["Rentals"]
    ROOT --> VAC["Vacant"]
    ROOT --> UNOCC["Unoccupied"]
    ROOT --> SALE["For Sale"]

    %% Rentals
    RENT --> R_NP["No Primary w/ Stand"]
    RENT --> R_P["Primary w/ Stand"]
    R_NP --> TIER1["Tier 1 broker"]
    R_NP --> LEAD["Lead line for larger desirable account"]
    R_NP --> WELL["Well-managed property in excess of $5m Cov A"]
    R_NP --> NOEX["No Justifiable Exception"]
    TIER1 --> W15["Write w/ 15% surcharge"]
    LEAD --> W15
    WELL --> W15
    NOEX --> DECLINE
    R_P --> LONG["Long term"]
    R_P --> SHORT["Short-term"]
    LONG --> W15
    SHORT --> W15STR["Write w/ 15% surcharge and attach STR EN"]

    %% Vacant / Unoccupied
    VAC --> V_NP["No Primary w/ Stand"]
    VAC --> V_P["Primary w/ Stand"]
    UNOCC --> V_NP
    UNOCC --> V_P
    V_NP --> DECLINE
    V_P --> LT60["Less than 60 days"]
    V_P --> GT60["Greater than 60 days"]
    LT60 --> MODS["Consider w/ Modifications for duration of non-occupancy:<br/>• 25% surcharge<br/>• 100k AOP<br/>• 3% Water cover<br/>• Low temperature alarm or winterized in cold climates<br/>• Twice-weekly interior and exterior visits by someone..."]
    GT60 --> DECLINE

    %% For Sale
    SALE --> DECLINE
```

## Notes on the page

- Text box beside the root: "You can provide the quote without this information but you must follow up after"

## Reading notes

- Vacant and Unoccupied share the same pair of child boxes ("No Primary w/ Stand" and "Primary w/ Stand"); their connectors overlap on the board.
- Only Decline is colour-coded on this page; the surcharge and modification outcomes are plain white.
- "w/ Stand" refers to whether the property is the insured's primary residence insured with Stand (interpretation; not defined on the board).
- "STR EN" is not defined on the board (plausibly a short-term-rental endorsement).
- The overview page lists "Unrelated NIs" under Occupancy, which does not appear on this page.
