# Electrical Systems

FigJam page: **Electrical Systems**. Drill-down for *Construction → Electrical* on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Electrical Systems"}
    DECLINE["Decline"]
    class DECLINE decline

    ROOT --> KT["Knob and Tube Wiring"]
    ROOT --> PANEL["Service Panel"]
    KT --> ISO["Isolated"]
    KT --> WHOLE["Whole house"]
    PANEL --> LT120["Less than 120 Amp"]
    PANEL --> INELIG["Ineligible Panels"]

    ISO --> Q1["Tier one broker or rounded account?"]
    WHOLE --> Q2["Tier one broker or rounded account?"]
    LT120 --> Q2
    INELIG --> Q3["Tier one broker or rounded account?"]

    %% Q1: isolated knob and tube
    Q1 -->|No| Q1N_LOW["Low Draw Areas<br/>(Bedrooms, Hallways, Living & Dining Rooms)"]
    Q1 -->|No| Q1N_HIGH["High Draw Areas<br/>(Kitchens, Bathrooms, Equipment Rooms)"]
    Q1N_LOW --> Q1N_LOW_R["Require Replacement within First Term"]
    Q1N_HIGH --> DECLINE
    Q1 -->|Yes| Q1Y_HIGH["High Draw Areas<br/>(Kitchens, Bathrooms, Equipment Rooms)"]
    Q1 -->|Yes| Q1Y_LOW["Low Draw Areas<br/>(Bedrooms, Hallways, Living & Dining Rooms)"]
    Q1Y_HIGH --> Q1Y_HIGH_R["Require Replacement within UWing Period"]
    Q1Y_LOW --> Q1Y_LOW_R["Require Replacement within First Term"]

    %% Q2: whole-house knob and tube, or panel under 120 A
    Q2 -->|No| DECLINE
    Q2 -->|Yes| Q2Y_R["Require Replacement within UWing Period"]

    %% Q3: ineligible panels
    Q3 -->|No| DECLINE
    Q3 -->|Yes| Q3Y_R["Require Replacement within UWing Period"]
```

## Notes on the page

- Text box beside the root: "If knob and question is missing assume it based on year built (1950)" (read as: if the knob-and-tube answer is missing, infer it from year built, with 1950 as the cut-off).

## Reading notes

- "Yes"/"No" boxes on the board are folded into edge labels here.
- The replacement requirements are uncoloured (white) on the board.
- The overview page shows a different Electrical subtree (Accept / Require Electrical Inspection, 60-day deadlines). This page has no inspection option.
- "UWing Period" vs "First Term" and "Tier one broker or rounded account" are not defined on the board.
