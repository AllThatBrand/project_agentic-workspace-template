# Agent-Optimised Repo — Mermaid Diagrams

All diagrams from the workflow design session.

---

## Diagram 1 — Dual-Mode Workflow

```mermaid
flowchart TD
    subgraph INPUTS["Inputs"]
        E[Email]
        W[WhatsApp]
        S[Slack]
        J[JIRA ticket]
        M[Meeting]
        SC[Scheduled]
    end

    INPUTS --> IT

    IT["Intake & triage\nPM or CEO · decide mode A or B"]

    IT -->|Mode A| QE
    IT -->|Mode B| RF

    subgraph MODEA["Mode A — Lightweight"]
        QE["Quick execution\nDeveloper or CEO · agent optional"]
        QE --> SN1[/"memory/ session note"/]
        SN1 --> CL["⚠ output lands anywhere"]
        CL --> RR["Resolve & reply"]
    end

    subgraph MODEB["Mode B — Full Scrum"]
        RF["Refinement\nCEO + PM · daily 08:00"]
        RF --> DC1[/"docs/decisions/ · JIRA updated"/]
        DC1 --> GR["Grooming\nAll · Friday 19:00 · estimate"]
        GR --> SP["Sprint planning\nAll · Sunday 19:00 · scope"]
        SP --> TS[/"tasks/current-sprint.md"/]
    end

    TS --> EX
    RR --> EX

    subgraph EX["Execution"]
        SV["Developer\nDevelops · runs agent"]
        AI["AI Agent\nWrites & edits code"]
        MA["PM + CEO\nCoordinates · reviews"]
        SL["QA\nTests DoD criteria"]
        SN2[/"memory/ session note"/]
    end

    EX --> DC["Deploy & close\nDeploy · close JIRA · inform client"]
    DC --> DC2[/"docs/decisions/ if architectural · JIRA closed"/]
```

---

## Diagram 2 — Daily Digest Automation Pipeline

```mermaid
flowchart TD
    CRON["3 AM · n8n cron"]

    CRON --> SLACK["Slack API\nproject channels · last 24h"]
    CRON --> GMAIL["Gmail API\nclient threads · last 24h"]

    SLACK --> MERGE
    GMAIL --> MERGE
    MERGE["Merge sources\nadd source field per item"]

    MERGE --> CLAUDE["Claude · classify & draft\ngroups by project · outputs CSV"]

    CLAUDE --> PR["GitHub PR created\ndigest/YYYY-MM-DD · n8n via API"]

    PR --> PM["PM reviews & merges\nreads CSV · approves"]

    PM --> GHA["GitHub Actions routes files\ncommits to correct repo folders"]

    GHA --> REPO["Repo updated\nagent has context for tomorrow"]

    note1["PR contains:\n· one CSV per digest\n· typed + dated rows"]
    note2["Classifies as:\n· decision\n· client-comms\n· question\n· mode-a"]

    CLAUDE -.-> note2
    PR -.-> note1
```

---

## Diagram 3 — Session Sync System (Stale Context Fix)

```mermaid
flowchart LR
    subgraph P1["Part 1 · auto on every merge"]
        GHA1["GitHub Actions\ncontext-update.yml"]
        CTX[".agent/CONTEXT.md\nalways current · ≤300 words"]
        GHA1 -->|regenerates| CTX
        CTX -->|contains| C1["· last updated timestamp\n· active sprint summary\n· last 3 decisions\n· open Mode A items"]
    end

    subgraph P2["Part 2 · local users (Cursor / VS Code)"]
        SK["start-session skill\nrun once at session start"]
        SK --> A1["1. git pull --rebase"]
        SK --> A2["2. git log · show delta"]
        SK --> A3["3. print CONTEXT.md"]
        SK --> A4["4. open in editor"]
        CR[".cursorrules\nread CONTEXT.md before any task"]
    end

    subgraph P3["Part 3 · Claude.ai web users"]
        PI["Claude.ai project instructions\npin CONTEXT.md URL"]
        SC["Session start convention\npaste CONTEXT.md as first message"]
    end

    CTX --> P2
    CTX --> P3
```

---

## Diagram 4 — Sync Rules Overview

```mermaid
flowchart LR
    R1T["Every merge\nany → main"] -->|GH Actions\ncontext-update.yml| R1O[".agent/CONTEXT.md"]

    R2T["Digest PR merge\ndigest/* → main"] -->|GH Actions\ndigest-router.yml| R2O["docs/\nmemory/"]
    R2O -->|triggers| R1O

    R3T["3 AM · daily\ncron"] -->|n8n\ndaily-digest| R3O["digest/YYYY-MM-DD.csv\nPR awaits PM"]

    R4T["Sunday 20:00\nafter planning"] -->|n8n\nsprint-sync| R4O["tasks/current-sprint.md"]
    R4O -->|triggers| R1O

    R5T["Slack /session\nweb users"] -->|n8n\nsession-webhook| R5O["memory/sessions/\nYYYY-MM-DD.md"]
    R5O -->|triggers| R1O

    style R1O fill:#E1F5EE,stroke:#0F6E56
    style R2O fill:#E1F5EE,stroke:#0F6E56
    style R3O fill:#F1EFE8,stroke:#5F5E5A
    style R4O fill:#E1F5EE,stroke:#0F6E56
    style R5O fill:#E1F5EE,stroke:#0F6E56
```

---

## Diagram 5 — Folder Structure & Ownership

```mermaid
flowchart TD
    ROOT["project-root/"]

    ROOT --> AGENT[".agent/"]
    ROOT --> DOCS["docs/"]
    ROOT --> TASKS["tasks/"]
    ROOT --> MEM["memory/"]
    ROOT --> DIG["digest/"]
    ROOT --> SCRIPTS["scripts/"]
    ROOT --> GH[".github/workflows/"]
    ROOT --> WEB["website/ (submodule)"]

    AGENT --> CTX[("CONTEXT.md\n🤖 auto · every merge")]
    AGENT --> PROJ[("project.md\n👤 human · once")]
    AGENT --> INST[("instructions.md\n👤 human · once")]
    AGENT --> SK["skills/"]
    SK --> SS[("start-session.md\n🛠 agent skill")]
    SK --> LM[("log-mode-a.md\n🛠 agent skill")]
    SK --> ES[("end-session.md\n🛠 agent skill")]

    DOCS --> DEC[("decisions/\n🤖 auto · digest")]
    DOCS --> SPEC[("specs/sow-shared.md\n👤 human · kickoff")]
    DOCS --> CC[("client-comms/\n🤖 auto · digest")]

    TASKS --> CS[("current-sprint.md\n🤖 auto · Sunday")]
    TASKS --> BL[("backlog.md\n👤 human")]

    MEM --> QT[("quick-tasks.md\n🛠 agent skill")]
    MEM --> SESS[("sessions/YYYY-MM-DD.md\n🛠 agent skill")]

    DIG --> DCSV[("YYYY-MM-DD.csv\n🤖 auto · n8n PR")]

    SCRIPTS --> GCP[("generate-context.py\n🤖 GH Actions")]
    SCRIPTS --> RDP[("route-digest.py\n🤖 GH Actions")]

    GH --> CUY[("context-update.yml")]
    GH --> DRY[("digest-router.yml")]
```

---

## Diagram 6 — Digest CSV Routing Logic

```mermaid
flowchart TD
    CSV["digest/YYYY-MM-DD.csv\ntype;project;title;content"]

    CSV --> PARSE["parse_csv()\nline.split(';', 3)\nmaxsplit=3 — content is safe"]

    PARSE --> VAL{"validate_row()\ntype · project · title\nrequired?"}

    VAL -->|missing fields| ERR["✗ skip row\nlog error\nsys.exit(1)"]
    VAL -->|unknown type| ERR

    VAL -->|decision| RD["route_decision()\ndocs/decisions/\nYYYY-MM-DD-proj-slug.md"]
    VAL -->|client-comms| RC["route_client_comms()\ndocs/client-comms/\nYYYY-MM-DD-proj-slug.md"]
    VAL -->|question| RQ["route_question()\n[question] prefix\n→ docs/client-comms/"]
    VAL -->|mode-a| RM["route_mode_a()\nappend row to\nmemory/quick-tasks.md"]
```

---

*Generated from the agent-optimised repo design session.*
