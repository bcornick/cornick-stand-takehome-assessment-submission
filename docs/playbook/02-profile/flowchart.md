# Profile

FigJam page: **Profile**. Drill-down for the *Profile* criterion on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Profile<br/>KYC > 5"}
    DECLINE["Decline"]
    class DECLINE decline

    ROOT --> REP["Reputational Damage to Stand"]
    ROOT --> SPOT["KYC 6 or 7 and In the Spotlight"]
    ROOT --> PRIV["KYC 6 or 7 but Private"]
    ROOT --> HIGH["KYC 8-10"]

    REP --> DECLINE

    SPOT --> SPOT1["Exclude Liability"]
    SPOT1 --> SPOT2["If Exclusion is deal killer"]
    SPOT2 --> SPOT3["Add<br/>• Social Media Exclusion<br/>• Libel/Slander Exclusion<br/>• Defense w/in Limits"]
    SPOT3 --> SPOT4["If D w/in L is deal killer"]
    SPOT4 --> SPOT5["Add<br/>• Social Media Exclusion<br/>• Libel/Slander Exclusion<br/>• Premises Liability Only"]
    SPOT5 --> SPOT6["If any are deal killers"]
    SPOT6 --> DECLINE

    PRIV --> PRIV1["Exclude Liability"]
    PRIV1 --> PRIV2["If Exclusion is deal killer"]
    PRIV2 --> PRIV3["Premises Liability Only"]
    PRIV3 --> PRIV4["If Premises Only is deal killer"]
    PRIV4 --> PRIV_FAV["And Profile Skews More Favorable"]
    PRIV4 --> PRIV_ADV["And Profile Skews More Adverse"]
    PRIV_FAV --> ACCEPT["Accept as is"]
    PRIV_ADV --> DECLINE
    class ACCEPT ok

    HIGH --> HIGH1["Exclude Liability"]
    HIGH1 --> HIGH2["If Exclusion is deal killer"]
    HIGH2 --> DECLINE
```

## Notes on the page

- Text box beside the root: "If KYC is missing Look up name on Facebook and google. Explicitly look for their involvement in lawsuits"
- Every decline path on this page ends in the same single Decline box on the board.

## Reading notes

- Each branch is a ladder of fallbacks: apply the first remedy; only if the broker/insured treats it as a deal killer, move to the next box.
- The root reads "KYC > 5", but "Reputational Damage to Stand" sits beside the KYC bands as a fourth branch rather than a KYC band. The KYC scale itself is not defined on the board.
