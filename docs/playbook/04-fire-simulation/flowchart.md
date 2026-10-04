# Fire Simulation

FigJam page: **Fire Simulation**. Drill-down for the *Fire Simulation* criterion on the Decision Points page.

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    ROOT{"Fire Simulation"}
    ROOT --> FAIL["Fail"]
    ROOT --> DNW["Do Not Write"]
    FAIL --> D_FAIL["Decline"]
    FAIL --> LEGACY["Consider Legacy UWing"]
    DNW --> LEGACY
    DNW --> D_DNW["Decline"]

    LEGACY --> MAP["Map risk Via Google maps / zillow"]
    LEGACY --> C7A["7a Compliant"]
    LEGACY --> MIND["Min Distance to neighbors home"]

    %% Map risk branch
    MAP --> ACCESS["Check Access"]
    MAP --> VEG["Assess Vegetation"]
    ACCESS --> INGRESS["Ingress/Egress"]
    ACCESS --> TURN["Responder turn-around"]
    INGRESS --> LIMITED["Limited"]
    INGRESS --> MULTI["Multiple points"]
    TURN --> SUFF["Sufficient"]
    TURN --> INSUFF["Insufficient"]
    LIMITED --> D_LIM["Decline"]
    MULTI --> CTQ_A["Continue to Quote"]
    SUFF --> CTQ_A
    INSUFF --> D_INS["Decline"]
    CTQ_A --> MITIG["Determine preliminary mitigation plan to discuss with broker"]

    VEG --> HEAVY["Heavy"]
    VEG --> MODL["Moderate / Light"]
    HEAVY --> WILL["Determine client willingness to mitigate greater distance"]
    MODL --> SLOPE["Check Slope"]
    SLOPE --> STEEP["Steep Slope increases clearance needs"]
    SLOPE --> GENTLE["Gentle / Level"]
    STEEP --> WILL
    GENTLE --> QUOTE["Quote"]

    %% 7a branch
    C7A -->|No| WILL
    C7A -->|Yes| CTQ_B["Continue to Quote"]

    %% Min distance branch
    MIND --> ADEQ["Adequate"]
    MIND --> CLOSE["Too Close"]
    ADEQ --> CTQ_B
    CLOSE --> D_CLOSE["Decline"]
    CTQ_B --> QUOTE

    %% Willingness outcome
    WILL -->|Yes| QUOTE
    WILL -->|No| D_LIM

    QUOTE --> MITIG

    ZILLOW["zillow"]

    class D_FAIL,D_DNW,D_LIM,D_INS,D_CLOSE decline
    class QUOTE ok
```

## Reading notes

- "Fail" and "Do Not Write" each branch to both Decline and Consider Legacy UWing. The board gives no criterion for choosing between them.
- "Determine client willingness…" = No leads to the Decline box under "Limited" (on the board: willingness → "No" box → that Decline box). "Yes"/"No" boxes are folded into edge labels here.
- The "Continue to Quote" box in the Check Access branch connects straight to "Determine preliminary mitigation plan…", bypassing the green "Quote" box.
- A standalone box labelled "zillow" sits beside "Map risk Via Google maps / zillow" with no connectors.
- Undefined on the board: "Legacy UWing", "7a Compliant", and what the simulation's Fail / Do Not Write results are based on.
