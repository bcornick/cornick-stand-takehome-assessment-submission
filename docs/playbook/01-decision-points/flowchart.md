# Decision Points (overview)

FigJam page: **Decision Points**. This page is the overview: it lists the top-level underwriting criteria and partially expands some of them. Most criteria have a more detailed page of their own (see *Drill-down pages* below).

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000
    classDef criterion fill:#dff3df,stroke:#6aa84f,color:#000
    classDef criterionOutline fill:#ffffff,stroke:#34c759,stroke-width:2px,color:#000
    classDef criterionStrong fill:#c3ecc3,stroke:#34c759,stroke-width:2px,color:#000

    OCC{"Occupancy"}
    PRO{"Profile"}
    FIRE{"Fire Simulation"}
    PC{"Protection Class 9 & 10"}
    CON{"Construction"}
    ANI{"Animals"}
    TRU{"Trusts & LLCs"}
    RC{"Replacement Cost"}
    class OCC,PRO,FIRE,PC,ANI,TRU,RC criterion
    class CON criterionOutline

    %% Occupancy
    OCC --> OCC_R["Rentals"]
    OCC --> OCC_V["Vacant"]
    OCC --> OCC_U["Unrelated NIs"]
    OCC_R --> OCC_RS["Short-term"]
    OCC_R --> OCC_RL["Long term"]

    %% Profile
    PRO --> PRO_H["High Profile"]
    PRO --> PRO_A["Adverse"]
    PRO_H --> PRO_REP["Reputational Damage to Stand"]
    PRO_H --> PRO_MIT["Mitigable"]
    PRO_REP --> PRO_D1["Decline"]
    PRO_MIT --> PRO_D2["Decline"]
    PRO_MIT --> PRO_EX["Exclude Liability"]
    PRO_MIT --> PRO_SM["Social Media Exclusion"]
    PRO_MIT --> PRO_LS["Libel/Slander Exclusion"]
    PRO_MIT --> PRO_DL["Defense w/in limits"]

    %% Construction
    CON --> CON_ROOF["Roof Class"]
    CON --> CON_SID["Siding"]
    CON --> CON_PP["Post and Pier"]
    CON --> CON_PL["Plumbing"]
    CON --> CON_EL["Electrical"]
    CON --> CON_SP["Swimming Pools"]
    CON --> CON_OAN["Other attractive nuisances"]
    class CON_ROOF,CON_SID,CON_PP,CON_EL,CON_SP,CON_OAN criterion
    class CON_PL criterionStrong

    CON_EL --> EL_KT["Knob and Tube"]
    CON_EL --> EL_PAN["Electrical Panel"]
    EL_KT --> EL_ISO["Isolated"]
    EL_KT --> EL_WH["Whole house"]
    EL_ISO --> EL_HI["High draw areas"]
    EL_ISO --> EL_LO["Low draw areas"]
    EL_HI --> EL_D1["Decline"]
    EL_LO --> EL_ACC["Accept"]
    EL_LO --> EL_D2["Decline"]
    EL_LO --> EL_INS["Require Electrical Inspection"]
    EL_LO --> EL_REP["Require Replacment"]
    EL_INS --> EL_INS60["Within 60 days"]
    EL_INS --> EL_INST["Within 1st term"]
    EL_REP --> EL_REP60["Within 60 days"]
    EL_REP --> EL_REPT["Within 1st term"]
```

Fire Simulation, Protection Class 9 & 10, Animals, Trusts & LLCs and Replacement Cost have no children on this page.

## Notes on the page

- Sticky note: "Be Sure to check other Pages for deeper drill downs"
- Colour on this page marks the top-level criteria and Construction sub-criteria (green), not outcomes. Decline boxes on this page are uncoloured.
- Two criteria are styled differently on the board: the Construction diamond has a white fill with a bright green outline, and the Plumbing box has a darker green fill with a bright green outline. The chart mirrors both; the board gives no meaning for the difference.

## Reading notes

- The board draws no arrow from "Mitigable" to the leftmost "Decline" box in its row (only four arrows, to the exclusion boxes). The board owner confirmed the fifth arrow to Decline is intended, so it is drawn here.
- "Require Replacment" is spelled that way on the board.

## Drill-down pages

| Criterion on this page | Detail page folder |
|---|---|
| Occupancy | `03-occupancy` |
| Profile | `02-profile` |
| Fire Simulation | `04-fire-simulation` |
| Protection Class 9 & 10 | `13-protection-class-9-and-10` |
| Construction → Roof Class | `05-roof-class` |
| Construction → Siding | `06-siding` |
| Construction → Post and Pier | `07-post-and-pier-foundations` |
| Construction → Plumbing | `08-plumbing` |
| Construction → Electrical | `09-electrical-systems` |
| Construction → Swimming Pools | `10-swimming-pools` |
| Trusts & LLCs | `11-trusts-and-llcs` |
| Replacement Cost | `12-replacement-cost` |
| Animals | none on the board |
| Construction → Other attractive nuisances | none on the board |

## Differences from the detail pages

- **Occupancy:** this page shows Rentals / Vacant / Unrelated NIs; the Occupancy page shows Rentals / Vacant / Unoccupied / For Sale.
- **Electrical:** this page offers Accept and Require Electrical Inspection with "within 60 days / within 1st term" deadlines; the Electrical Systems page offers replacement only, with "within First Term / within UWing Period" deadlines, and routes through a "Tier one broker or rounded account?" question.
- **Profile:** this page shows High Profile / Adverse; the Profile page branches on KYC score bands.
