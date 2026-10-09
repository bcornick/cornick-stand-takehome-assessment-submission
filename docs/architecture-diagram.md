# Architecture diagrams

Seven views, from the outside in. `ARCHITECTURE.md` explains the reasoning; these show the shape. The diagrams are Mermaid, which GitHub renders in place.

**Legend:** blue boxes are this submission, grey boxes are Stand's services, orange boxes are external model services, and green boxes are stand-ins for services not yet wired in. Solid arrows are calls or data flow; dotted arrows are reads of stored data.

## 1. System context

Who and what the system talks to.

```mermaid
flowchart LR
    UW(["Underwriter"])
    PR(["Producer"])

    subgraph SUB["Underwriting triage harness"]
        APP["Triage app<br/>workflow, skills, evals"]
    end

    LG["Stand lead generator<br/>ten leads per seed"]
    MB["Stand mock mailbox<br/>email out, replies tracked"]
    DS["DeepSeek<br/>deepseek-flash"]
    JV["Jev, TypeSafe<br/>reply classification"]
    SI["Stand-in data services<br/>replacement cost, PPC, KYC,<br/>fire model, geospatial"]

    UW -- "reviews, decides, asks questions" --> APP
    APP -- "queue, cards, reasons, evidence" --> UW
    LG -- "morning queue" --> APP
    APP -- "requests, quotes, decline notices" --> MB
    MB -- "emails" --> PR
    PR -- "replies, through the paste box or stored fixtures" --> APP
    APP -- "read replies, soften emails, chat" --> DS
    APP -- "classify replies" --> JV
    APP -. "look up system-owned fields" .-> SI

    classDef ours fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3a
    classDef stand fill:#e5e7eb,stroke:#4b5563,color:#111827
    classDef ext fill:#ffedd5,stroke:#c2410c,color:#431407
    classDef stub fill:#dcfce7,stroke:#15803d,color:#052e16
    class APP ours
    class LG,MB stand
    class DS,JV ext
    class SI stub
```

## 2. Containers

What runs, as defined in `compose.yaml`. `make up` starts the demo stack; `make eval` starts the eval profile with its own copies of Stand's services, so an eval run never touches the demo.

```mermaid
flowchart TB
    BR(["Browser"])

    subgraph DEMO["Demo stack: make up"]
        APPC["app<br/>FastAPI + built React UI<br/>port 8000"]
        DB[("SQLite<br/>event log + fact ledger<br/>volume app-data")]
        LGC["leadgen<br/>Stand, unmodified<br/>port 8081"]
        MBC["mailbox<br/>Stand, unmodified<br/>port 8025"]
    end

    subgraph EVAL["Eval profile: make eval"]
        EVC["eval runner<br/>graders, controls, labels<br/>always replay"]
        LGE["leadgen-eval"]
        MBE["mailbox-eval"]
    end

    REC[("recordings/<br/>model and Jev exchanges")]
    RES[("evals/results.jsonl<br/>one row per run")]
    MODELS["DeepSeek and Jev<br/>live and record modes only"]

    BR --> APPC
    APPC --> DB
    APPC --> LGC
    APPC --> MBC
    APPC -. "replay mode" .-> REC
    APPC -- "live and record modes" --> MODELS
    EVC --> LGE
    EVC --> MBE
    EVC -. "replay" .-> REC
    EVC -- "append" --> RES

    classDef ours fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3a
    classDef stand fill:#e5e7eb,stroke:#4b5563,color:#111827
    classDef ext fill:#ffedd5,stroke:#c2410c,color:#431407
    classDef store fill:#f8fafc,stroke:#64748b,color:#0f172a
    class APPC,EVC ours
    class LGC,MBC,LGE,MBE stand
    class MODELS ext
    class DB,REC,RES store
```

## 3. Components inside the app

Every change goes through the command layer, and every actor reaches it the same way. The transport sets the actor, never a model.

```mermaid
flowchart TB
    subgraph ACTORS["Actors"]
        direction LR
        UI["React UI<br/>lead list, conversations,<br/>cards, panel"]
        CHAT["Assistant: chat skill<br/>7 lookups, at most 8 steps,<br/>can only propose"]
        REPLY["Reply endpoint<br/>POST /api/replies"]
    end

    API["HTTP API, FastAPI"]
    CMD["Command layer<br/>typed commands, actor checks,<br/>approvals bound to a hash of the exact text"]
    WF["Workflow<br/>fixed steps per lead, up to 4 leads at once"]

    subgraph SKILLS["Skills: each has a manifest with trigger, allowed commands and fallback"]
        direction LR
        T["triage_fields"] --> R["resolve_data"] --> E["evaluate_playbook"] --> P["plan_asks"] --> RM["render_message"] --> PM["polish_message<br/>model"]
        Q["build_quote_packet"]
        RR["read_reply<br/>Jev, then model"]
    end

    subgraph DATA["Reference data"]
        direction LR
        RULES["Rules core<br/>Stand's registry, 7 playbook graphs,<br/>interpretation table, wording"]
        PROV["Stand-in providers<br/>world-42.json"]
    end

    MODEL["Model client<br/>live, record or replay"]
    LOG[("Event log + fact ledger<br/>every value has a source,<br/>every decision a reason")]
    SEND["Send path<br/>draft, dispatching, sent or unknown;<br/>no automatic resend"]
    MB["Stand mailbox"]

    UI --> API --> CMD
    CHAT -- "proposals" --> CMD
    REPLY -- "deliver_reply" --> CMD
    CMD -- "start a run, re-run a lead" --> WF
    WF -- "runs the steps in order" --> SKILLS
    CMD -- "a delivered reply runs read_reply" --> SKILLS
    SKILLS -. "reads" .-> DATA
    SKILLS -- "model skills only" --> MODEL
    CHAT --> MODEL
    WF -- "drafts, items, facts" --> CMD
    CMD --> LOG
    CMD --> SEND --> MB

    classDef ours fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3a
    classDef modelskill fill:#ffedd5,stroke:#c2410c,color:#431407
    classDef stub fill:#dcfce7,stroke:#15803d,color:#052e16
    classDef stand fill:#e5e7eb,stroke:#4b5563,color:#111827
    classDef store fill:#f8fafc,stroke:#64748b,color:#0f172a
    class UI,REPLY,WF,API,CMD,T,R,E,P,RM,Q,SEND,RULES ours
    class CHAT,PM,RR,MODEL modelskill
    class PROV stub
    class MB stand
    class LOG store
```

Orange marks the three places a model is used: reading replies, softening request emails, and the assistant.

## 4. The life of a lead

Where each lead can end: a quote sent, one request sent to the producer, or a clear question for the underwriter.

```mermaid
flowchart TD
    A["Lead arrives from the queue"] --> B["Triage fields against Stand's registry"]
    B --> C["Resolve data:<br/>look up, derive or assume"]
    C --> D["Evaluate the playbook pages that apply"]
    D --> E{"What does the plan say?"}

    E -- "proposed decline" --> F["Draft decline notice"]
    F --> G{{"Underwriter approves,<br/>with a reason"}}
    G --> H["Decline notice sent"]

    E -- "a choice the playbook leaves open" --> I{{"Underwriter decides"}}
    I -- "decline" --> F
    I -- "continue" --> D

    E -- "information missing" --> J["Plan the asks, render the request,<br/>model softens the opening and closing"]
    J --> K{"Could an open choice<br/>still decline the lead?"}
    K -- "yes" --> L{{"Held: underwriter sends it<br/>or declines"}}
    K -- "no, routine" --> M["Request sent: one per round"]
    L --> M
    M --> N["Producer replies"]
    N --> O["read_reply: values with<br/>the exact words they came from"]
    O --> P{"Contradicts a value on file?"}
    P -- "yes" --> Q{{"Underwriter reviews"}}
    P -- "no" --> B
    Q --> B

    E -- "nothing missing, nothing to decide" --> R["Draft quote packet"]
    R --> S{{"Underwriter approves"}}
    S --> T["Quote sent"]

    classDef human fill:#fef9c3,stroke:#a16207,color:#422006
    classDef done fill:#dcfce7,stroke:#15803d,color:#052e16
    class G,I,L,Q,S human
    class H,T,M done
```

Yellow hexagons are where the underwriter decides; green boxes are messages that go out. After two request rounds without a resolution, the lead goes to the underwriter.

## 5. A reply, round trip

Lead 008: a request is out, the producer replies, and a quote goes out on approval.

```mermaid
sequenceDiagram
    autonumber
    actor PR as Producer
    participant API as Reply endpoint
    participant RR as read_reply
    participant JV as Jev
    participant DS as DeepSeek
    participant CMD as Command layer
    participant LOG as Event log + ledger
    participant WF as Workflow
    actor UW as Underwriter
    participant SEND as Send path
    participant MB as Mailbox

    PR->>API: reply text
    API->>CMD: deliver_reply, as the inbound actor
    CMD->>RR: read against the open request's asks
    RR->>JV: classify the reply
    JV-->>RR: probabilities per type
    RR->>DS: one call: the values and a classification
    DS-->>RR: values, with the words they came from
    alt Jev's confidence at or above 0.70
        RR->>RR: Jev's classification stands
    else below 0.70 or Jev unavailable
        RR->>RR: the model's classification stands
    end
    RR->>RR: code checks each quote, drops what was not asked
    RR-->>CMD: the reading
    CMD->>LOG: reply values enter the ledger
    CMD->>WF: re-run the lead from the top
    WF->>CMD: draft the quote packet
    CMD->>LOG: open an item for the underwriter
    UW->>CMD: Send quote, bound to the packet's hash
    CMD->>SEND: dispatch
    SEND->>LOG: mark dispatching
    SEND->>MB: post the packet
    MB-->>SEND: accepted
    SEND->>LOG: mark sent
```

## 6. The eval harness

`make eval` refuses uncommitted code, so every result row names the code it measured.

```mermaid
flowchart LR
    subgraph TRUTH["Sources of truth"]
        LB["Lead labels<br/>written from the playbook,<br/>signed by a person"]
        AK["Stand's answer key<br/>regenerated per seed"]
        RL["Reply labels,<br/>3 of 8 held back"]
        CS["Case tables<br/>per playbook page,<br/>reply reading, chat"]
    end

    MK["make eval"] --> CT{"Working tree<br/>committed?"}
    CT -- "no" --> X["Refused"]
    CT -- "yes" --> RUN["Eval container, replay:<br/>fresh leadgen and mailbox"]
    RUN --> FP["First pass:<br/>ten leads settle"]
    FP --> G1["Grade"]
    G1 --> SA["Scripted underwriter actions<br/>and producer replies"]
    SA --> G2["Grade again"]

    LB --> G1
    LB --> G2
    AK --> G1
    RL --> G2
    CS --> G2

    G2 --> GR["9 graders:<br/>Coverage, One open request, Asks,<br/>Forbidden asks, Rule trace,<br/>Packet fidelity, Send safety,<br/>Stand's key, Reply reading"]
    GR --> CE{"Any critical error?<br/>double send, unapproved send,<br/>missing requirement,<br/>reply approving an action"}
    CE --> ROW[("results.jsonl:<br/>commit, prompt versions,<br/>hypothesis, scores")]
    ROW --> DEC["Person adds a decision row:<br/>keep or discard, and why"]

    CTRL["Controls: do nothing, email everything,<br/>send twice. Each must be caught."] --> RUN

    classDef ours fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3a
    classDef truth fill:#fef9c3,stroke:#a16207,color:#422006
    classDef store fill:#f8fafc,stroke:#64748b,color:#0f172a
    class MK,RUN,FP,G1,SA,G2,GR,CE,DEC,CTRL,CT,X ours
    class LB,AK,RL,CS truth
    class ROW store
```

## 7. Repository map

```mermaid
flowchart LR
    ROOT["repo root"]
    ROOT --> SRC["src/uwh/<br/>the application"]
    ROOT --> WEB["web/<br/>React UI"]
    ROOT --> EV["evals/<br/>runner, graders, controls,<br/>labels, results.jsonl"]
    ROOT --> RECD["recordings/<br/>model and Jev exchanges"]
    ROOT --> FX["fixtures/replies/<br/>producer replies,<br/>held/ kept back"]
    ROOT --> TS["tests/<br/>fast, slow, integration"]
    ROOT --> TL["tools/ and scripts/<br/>fresh-clone rehearsal,<br/>data capture, checks"]
    ROOT --> SIM["sim-harness/<br/>Stand's services, unmodified"]
    ROOT --> DOCS["docs/<br/>brief, playbook, eval loop,<br/>build_logs"]

    SRC --> RT["runtime/<br/>commands, events, ledger,<br/>send path, workflow, model client"]
    SRC --> RU["rules/<br/>registry, triage, graph interpreter,<br/>validators, data/"]
    SRC --> SK["skills/<br/>one folder per skill:<br/>manifest, code, prompt, cases"]
    SRC --> CH["chat/<br/>assistant skill and lookups"]
    SRC --> AP["api/<br/>FastAPI routes and views"]
    SRC --> PV["providers/<br/>stand-in lookups"]

    classDef ours fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3a
    classDef stand fill:#e5e7eb,stroke:#4b5563,color:#111827
    class ROOT,SRC,WEB,EV,RECD,FX,TS,TL,DOCS,RT,RU,SK,CH,AP,PV ours
    class SIM stand
```
