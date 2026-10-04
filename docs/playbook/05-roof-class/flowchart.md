# Roof Class

FigJam page: **Roof Class**. Drill-down for *Construction → Roof Class* on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Roof Class"}
    ROOT --> CA["Class A"]
    ROOT --> NCA["Non-Class A"]
    ROOT --> UNK["Unknown Class"]

    CA --> OK_A["Okay to Quote"]

    %% Non-Class A
    NCA --> N_LO["P(F) ≤ .15"]
    NCA --> N_MID["P(F) > .15 and < .50"]
    NCA --> N_HI["P(F) > .50"]
    N_LO --> OK_B["Okay to Quote"]
    N_MID --> N_MID_R["Require confirmation of Class A or replacement within first term"]
    N_HI --> N_HI_R["Require confirmation of Class A or replacement within first 60 days or Decline"]

    %% Unknown Class
    UNK --> U_LO["P(F) ≤ .15"]
    UNK --> U_MID["P(F) > .15 and ≤ .50"]
    UNK --> U_HI["P(F) > .50"]
    U_LO --> OK_B

    U_MID --> U_MID_NC["• Composition/asphalt/fiberglass shingles, installed or replaced within the past 20 years<br/>• Concrete, clay, slate, and similar noncombustible roofing materials<br/>• Modern standing seam and other metal roofing systems"]
    U_MID --> U_MID_C["Combustible roofing materials, including untreated wood shake or shingle roofs, flat membrane roofs, tar & gravel"]
    U_MID_NC --> U_MID_OK["Assume Class A<br/>Okay to Quote"]
    U_MID_C --> U_MID_R["Require confirmation of Class A or replacement within first term<br/><br/>Acceptable evidence can include:<br/>• roofing permits<br/>• contractor invoices<br/>• manufacturer documentation<br/>• inspection findings<br/>• other documentation reasonably supporting Class A roof construction."]

    U_HI --> U_HI_NC["• Composition/asphalt/fiberglass shingles, installed or replaced within the past 20 years<br/>• Concrete, clay, slate, and similar noncombustible roofing materials<br/>• Modern standing seam and other metal roofing systems"]
    U_HI --> U_HI_C["Combustible roofing materials, including untreated wood shake or shingle roofs, flat membrane roofs, tar & gravel"]
    U_HI_NC --> U_HI_OK["Assume Class A<br/>Okay to Quote"]
    U_HI_C --> U_HI_R["Require confirmation of Class A or replacement within 60 days or decline<br/><br/>Acceptable evidence can include:<br/>• roofing permits<br/>• contractor invoices<br/>• manufacturer documentation<br/>• inspection findings<br/>• other documentation reasonably supporting Class A roof construction."]

    class OK_A,OK_B,U_MID_OK,U_HI_OK ok
    class N_MID_R,N_HI_R,U_MID_R,U_HI_R cond
```

## Reading notes

- The material-list boxes under Unknown Class have no heading on the board; they start directly with their bullets.
- Band labels on the board are written "P(F) < = .15", "P(F) > .15 < .50" (Non-Class A) and "P(F) > .15 < = .50" (Unknown Class); they are rewritten here with ≤ and "and".
- **Threshold gap:** for Non-Class A, P(F) = .50 falls in neither band (`< .50` and `> .50`). Unknown Class uses `≤ .50`.
- P(F) is not defined on the board (presumably a probability of failure from the fire simulation; unverified).
- Unknown Class with P(F) ≤ .15 connects to the same "Okay to Quote" box as Non-Class A with P(F) ≤ .15.
