# Protection Class 9 & 10

FigJam page: **PC 9 & 10**. Drill-down for the *Protection Class 9 & 10* criterion on the Decision Points page. This is the largest page on the board.

## Structure at a glance

The tree has three main branches. Several sub-blocks repeat across them:

- **Response Time** → Greater than 30 min (Decline) / Between 15 and 30 min / Within 15 min
- **Nearest Station Staffing** → Volunteer / Paid responders → home-size bands (> 7500, 4000–7500, < 4000 sq ft) → water and sprinkler requirements
- **Gates or Other Physical Barriers** → Knox Box requirement, or Central Station Fire Alarm check

| Branch | Path to it |
|---|---|
| A. Hydrant | Public hydrant within 1000' = Yes |
| B. Tankers | No hydrant → no alternative water source → tankers bring water |
| C. Alternative water source | No hydrant → alternative source (lake, pond, cistern, …) within 1000' and accessible year round |

The full chart is split into one Mermaid block per branch so each stays readable. Node IDs are prefixed by branch (`A_`, `B_`, `C_`).

## Screenshots

The page is too large to read in one image, so it is captured as an overview plus zoomed tiles:

| File | Shows |
|---|---|
| `screenshot-0-overview.png` | Whole page (layout only; text not legible) |
| `screenshot-1-root-and-hydrant-branch.png` | Root, hydrant question, Branch A down to Gates, top of Branches B and C |
| `screenshot-2-water-source-checks.png` | Branch C water-source checks (dry hydrant, fittings, paved roads); Branch A Gates/Alarm; part of Branch B within-15 staffing |
| `screenshot-3-tankers-branch.png` | All of Branch B; Branch C checks down to its Response Time |
| `screenshot-4-water-source-response-time.png` | Branch C Response Time and both staffing blocks |
| `screenshot-5-water-source-gates.png` | Branch C shared Gates / Central Station Fire Alarm step |

## Root

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000

    ROOT{"Protection Class 9 & 10 Questionnaire"}
    ROOT --> HYD["Public Hydrant within 1000'"]
    HYD -->|Yes| A["Branch A: Response Time"]
    HYD -->|No| ALT["Alternative Water Source Available such as Lake, Pond, River, Cistern, Tank, Swimming Pool"]
    ALT -->|No| TANK["Tankers Bring Water"]
    ALT -->|Yes| W1000["Within 1000' of Dwelling"]
    TANK -->|Yes| B["Branch B: road access, then Response Time"]
    TANK -->|No| D_ROOT["Decline"]
    W1000 -->|No| D_ROOT
    W1000 -->|Yes| C["Branch C: Water Source Accessible Year Round"]
    class D_ROOT decline
```

## Branch A: public hydrant within 1000'

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    A_RT["Response Time"]
    A_RT --> A_GT30["Greater than 30 Minutes"]
    A_RT --> A_1530["Between 15 and 30 Minutes"]
    A_RT --> A_W15["Within 15 Minutes"]
    A_GT30 --> A_D["Decline"]
    A_W15 --> A_OK["Okay to write"]
    A_1530 --> A_SIZE["Home is Under 7500 Square Feet"]
    A_SIZE -->|Yes| A_PROCEED["Okay to Proceed"]
    A_SIZE -->|No| A_SPRINK["Require Centrally Monitored Interior Sprinklers"]
    A_PROCEED --> A_GATES["Gates or Other Physical Barriers"]
    A_SPRINK --> A_GATES
    A_GATES -->|Yes| A_KNOX["Require Knox Box within UWing Period"]
    A_GATES -->|No| A_ALARM["Central Station Fire Alarm"]
    A_ALARM --> A_ALARM_REQ["Require within UWing Period"]
    A_ALARM --> A_ALARM_Y["Yes<br/>(no outcome drawn)"]

    class A_D decline
    class A_OK ok
    class A_SPRINK,A_KNOX,A_ALARM_REQ cond
```

## Branch B: tankers bring water

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    B_TANK_YES["Tankers Bring Water = Yes"]
    B_TANK_YES --> B_MORE["More than One Road Access Point to Home"]
    B_TANK_YES --> B_LIM["Limited Access, Dead-End Road, No Turn-Around"]
    B_LIM --> B_D_ROOT["Decline<br/>(same box as Tankers = No)"]
    B_MORE --> B_RT["Response Time"]
    B_RT --> B_GT30["Greater than 30 Minutes"]
    B_RT --> B_1530["Between 15 and 30 Minutes"]
    B_RT --> B_W15["Within 15 Minutes"]
    B_GT30 --> B_D_RT["Decline"]

    %% Within 15 minutes
    B_W15 --> B15_STAFF["Nearest Station Staffing"]
    B15_STAFF --> B15_VOL["Volunteer Responders"]
    B15_STAFF --> B15_PAID["Paid Responders"]
    B15_VOL --> B15_V_GT75["Home is Larger than 7500 Square Feet"]
    B15_VOL --> B15_V_MID["Home is Larger than 4000 Square Feet but Smaller than 7500 Square Feet"]
    B15_VOL --> B15_V_LT40["Home is Under 4000 Square Feet"]
    B15_V_GT75 --> B15_V_GT75_R["Require 10 Gallons Water per Square Foot and Centrally Monitored Interior Sprinklers"]
    B15_V_MID --> B15_V_SPR["Home has Centrally Monitored Interior Sprinklers"]
    B15_V_LT40 --> B15_V_SPR
    B15_V_SPR -->|No| B15_V_20["Require 20 Gallons Water per Square Foot"]
    B15_V_SPR -->|Yes| B15_V_10["Require 10 Gallons Water per Square Foot"]
    B15_PAID --> B15_P_GT75["Home is Larger than 7500 Square Feet"]
    B15_PAID --> B15_P_MID["Home is Larger than 4000 Square Feet but Smaller than 7500 Square Feet"]
    B15_PAID --> B15_P_LT40["Home is Under 4000 Square Feet"]
    B15_P_GT75 --> B15_P_GT75_R["Require 10 Gallons Water per Square Foot and Centrally Monitored Interior Sprinklers"]
    B15_P_MID --> B15_P_SPR["Home has Centrally Monitored Interior Sprinklers"]
    B15_P_LT40 --> B15_P_LT40_R["Require 10 Gallons Water per Square Foot"]
    B15_P_SPR -->|No| B15_P_20["Require 20 Gallons Water per Square Foot"]
    B15_P_SPR -->|Yes| B15_P_10["Require 10 Gallons Water per Square Foot"]

    %% Between 15 and 30 minutes
    B_1530 --> B30_STAFF["Nearest Station Staffing"]
    B30_STAFF --> B30_VOL["Volunteer Responders"]
    B30_STAFF --> B30_PAID["Paid Responders"]
    B30_VOL --> B30_V_GT75["Home is Larger than 7500 Square Feet"]
    B30_V_GT75 --> B30_V_D["Decline"]
    B30_PAID --> B30_P_GT75["Home is Larger than 7500 Square Feet"]
    B30_P_GT75 --> B30_P_GT75_R["Require 10 Gallons Water per Square Foot and Centrally Monitored Interior Sprinklers"]
    B30_VOL --> B30_MID["Home is Larger than 4000 Square Feet but Smaller than 7500 Square Feet"]
    B30_PAID --> B30_MID
    B30_VOL --> B30_LT40["Home is Under 4000 Square Feet"]
    B30_PAID --> B30_LT40
    B30_MID --> B30_SPR["Home has Centrally Monitored Interior Sprinklers"]
    B30_LT40 --> B30_SPR
    B30_SPR -->|No| B30_20["Require 20 Gallons Water per Square Foot"]
    B30_SPR -->|Yes| B30_10["Require 10 Gallons Water per Square Foot"]
    B30_20 --> B_GATES["Gates or Other Physical Barriers"]
    B30_10 --> B_GATES
    B_GATES -->|Yes| B_KNOX["Require Knox Box within UWing Period"]
    B_GATES -->|No| B_ALARM["Central Station Fire Alarm"]
    B_ALARM --> B_ALARM_REQ["Require within UWing Period"]
    B_ALARM --> B_ALARM_Y["Yes<br/>(no outcome drawn)"]

    class B_D_ROOT,B_D_RT,B30_V_D decline
    class B15_V_GT75_R,B15_V_20,B15_V_10,B15_P_GT75_R,B15_P_LT40_R,B15_P_20,B15_P_10 cond
    class B30_P_GT75_R,B30_20,B30_10,B_KNOX,B_ALARM_REQ cond
```

## Branch C: alternative water source within 1000'

```mermaid
flowchart TD
    classDef decline fill:#f8d7d7,stroke:#e06666,color:#000
    classDef ok fill:#dff3df,stroke:#6aa84f,color:#000
    classDef cond fill:#fbf1d0,stroke:#e6b800,color:#000

    C_WSA["Water Source Accessible Year Round"]
    C_WSA -->|No| C_D1["Decline"]
    C_WSA -->|Yes| C_DRY["Source has Dry Hydrant"]
    C_DRY -->|No| C_DRY_R["Require Dry Hydrant within UWing Period"]
    C_DRY -->|Yes| C_FIT["Both County and Cal Fire Fittings"]
    C_FIT -->|No| C_FIT_R["Require Retrofit within UWing Period"]
    C_FIT -->|Yes| C_PAVED["Paved Roads Accessible All Year"]
    C_PAVED -->|No| C_D2["Decline"]
    C_PAVED -->|Yes| C_MORE["More than One Road Access Point to Home"]
    C_PAVED -->|Yes| C_LIM["Limited Access, Dead-End Road, No Turn-Around"]
    C_LIM --> C_D3["Decline"]
    C_MORE --> C_RT["Response Time"]
    C_RT --> C_GT30["Greater than 30 Minutes"]
    C_RT --> C_1530["Between 15 and 30 Minutes"]
    C_RT --> C_W15["Within 15 Minutes"]
    C_GT30 --> C_D4["Decline"]

    %% Within 15 minutes
    C_W15 --> C15_STAFF["Nearest Station Staffing"]
    C15_STAFF --> C15_VOL["Volunteer Responders"]
    C15_STAFF --> C15_PAID["Paid Responders"]
    C15_VOL --> C15_V_GT75["Home is Larger than 7500 Square Feet"]
    C15_VOL --> C15_V_MID["Home is Larger than 4000 Square Feet but Smaller than 7500 Square Feet"]
    C15_VOL --> C15_V_LT40["Home is Under 4000 Square Feet"]
    C15_V_GT75 --> C15_V_GT75_R["Require 10 Gallons Water per Square Foot and Centrally Monitored Interior Sprinklers"]
    C15_V_MID --> C15_V_SPR["Home has Centrally Monitored Interior Sprinklers"]
    C15_V_LT40 --> C15_V_SPR
    C15_V_SPR -->|No| C15_V_20["Require 20 Gallons Water per Square Foot"]
    C15_V_SPR -->|Yes| C15_V_10["Require 10 Gallons Water per Square Foot"]
    C15_PAID --> C15_P_GT75["Home is Larger than 7500 Square Feet"]
    C15_PAID --> C15_P_MID["Home is Larger than 4000 Square Feet but Smaller than 7500 Square Feet"]
    C15_PAID --> C15_P_LT40["Home is Under 4000 Square Feet"]
    C15_P_GT75 --> C15_P_GT75_R["Require 10 Gallons Water per Square Foot and Centrally Monitored Interior Sprinklers"]
    C15_P_MID --> C15_P_SPR["Home has Centrally Monitored Interior Sprinklers"]
    C15_P_LT40 --> C15_P_SPR
    C15_P_SPR -->|No| C15_P_20["Require 20 Gallons Water per Square Foot"]
    C15_P_SPR -->|Yes| C15_P_10["Require 10 Gallons Water per Square Foot"]

    %% Between 15 and 30 minutes
    C_1530 --> C30_STAFF["Nearest Station Staffing"]
    C30_STAFF --> C30_VOL["Volunteer Responders"]
    C30_STAFF --> C30_PAID["Paid Responders"]
    C30_VOL --> C30_V_GT75["Home is Larger than 7500 Square Feet"]
    C30_V_GT75 --> C30_V_D["Decline"]
    C30_PAID --> C30_P_GT75["Home is Larger than 7500 Square Feet"]
    C30_P_GT75 --> C30_P_GT75_R["Require 10 Gallons Water per Square Foot and Centrally Monitored Interior Sprinklers"]
    C30_VOL --> C30_MID["Home is Larger than 4000 Square Feet but Smaller than 7500 Square Feet"]
    C30_PAID --> C30_MID
    C30_VOL --> C30_LT40["Home is Under 4000 Square Feet"]
    C30_PAID --> C30_LT40
    C30_MID --> C30_SPR["Home has Centrally Monitored Interior Sprinklers"]
    C30_LT40 --> C30_SPR
    C30_SPR -->|No| C30_20["Require 20 Gallons Water per Square Foot"]
    C30_SPR -->|Yes| C30_10["Require 10 Gallons Water per Square Foot"]

    %% Shared gates step for both response-time bands
    C15_V_GT75_R --> C_GATES["Gates or Other Physical Barriers"]
    C15_V_20 --> C_GATES
    C15_V_10 --> C_GATES
    C15_P_GT75_R --> C_GATES
    C15_P_20 --> C_GATES
    C15_P_10 --> C_GATES
    C30_20 --> C_GATES
    C30_10 --> C_GATES
    C_GATES -->|Yes| C_KNOX["Require Knox Box within UWing Period"]
    C_GATES -->|No| C_ALARM["Central Station Fire Alarm"]
    C_ALARM --> C_ALARM_REQ["Require within UWing Period"]
    C_ALARM --> C_ALARM_Y["Yes<br/>(no outcome drawn)"]

    class C_D1,C_D2,C_D3,C_D4,C30_V_D decline
    class C_DRY_R,C_FIT_R,C15_V_GT75_R,C15_V_20,C15_V_10,C15_P_GT75_R,C15_P_20,C15_P_10 cond
    class C30_P_GT75_R,C30_20,C30_10,C_KNOX,C_ALARM_REQ cond
```

## Notes on the page

- Text box beside the root: "If Missing Assume protection Class 9 and run through the diagram."
- The word "Questionnaire" under the root is underlined on the board (it may be a link that does not survive in a view-only session).

## Reading notes

- "Yes"/"No" boxes on the board are folded into edge labels, except where a "Yes" box has no outgoing arrow; those are kept as nodes marked "(no outcome drawn)".
- Under "Central Station Fire Alarm", one arrow goes to "Require within UWing Period" with no Yes/No box (read as: no alarm → require one), and one goes to a "Yes" box that leads nowhere.
- In both "Between 15 and 30 Minutes" staffing blocks (Branches B and C), the Volunteer and Paid connectors overlap on the board. Volunteer > 7500 → Decline; Paid > 7500 → 10 gallons + sprinklers; both Volunteer and Paid → 4000–7500 and < 4000 → sprinkler question.
- In Branch B, the "Volunteer > 7500 → Decline" connector has arrowheads at both ends on the board. The board owner confirmed this is an error (a Decline has no outgoing path, and the identical block in Branch C is one-way), so it is drawn one-way here.
- **Inconsistencies on the board:**
  - Branch B's "Within 15 Minutes" outcomes have no Gates step, while the sprinkler outcomes of Branch B's "Between 15 and 30" block, and every Branch C outcome except Paid > 7500 in its "Between 15 and 30" block, do.
  - In both "Between 15 and 30" blocks, the "Paid > 7500" outcome does not continue to the Gates step, while the sprinkler outcomes do.
  - Paid responders with a home under 4000 sq ft: Branch B goes straight to "Require 10 Gallons Water per Square Foot", while Branch C goes through the sprinkler question.
  - In Branch C, "Require Dry Hydrant…" and "Require Retrofit…" are terminal; the board does not show whether evaluation continues after them.
- Branch A's "Within 15 Minutes" goes straight to "Okay to write" with no Gates step.
