# Gantry Architecture

> Technical documentation for the Gantry Fleet Protocol (V6.5 Consultation Loop)

---

## Executive Summary

Gantry is a **production-grade AI software factory** that transforms natural language (and optional design images) into deployed applications. Unlike AI assistants that only generate code snippets, Gantry:

1. **Consults** via a CTO-style loop: propose plan → user feedback → confirm → build
2. **Builds** code in isolated Docker containers (Foundry)
3. **Tests** with self-healing (up to 3 retry attempts)
4. **Deploys** to Vercel with live URLs
5. **Publishes** via GitHub PR (never pushes to main) and **records** cryptographic audit evidence

---

## Architecture Overview (V6.5)

| Aspect | Current (V6.5) | Description |
|--------|----------------|-------------|
| **API** | Flask (sync) | Primary entry: `src/main.py`. REST only; status via polling. |
| **Consultation** | CTO Consultant | `src/core/consultant.py`. Multi-turn: propose → question → confirm → build. |
| **Orchestration** | Fleet Manager | `src/core/fleet.py`. `process_voice_input()` drives consultation then build. |
| **Auth** | Session + rate limit | `src/core/auth.py`. Password (SHA256) + per-IP rate limiting. |
| **Design Input** | Text + optional image | Image saved to `missions/{id}/design-reference.{ext}`, injected into pod by Foundry. |
| **Status** | Polling | `GET /gantry/status/<id>` and `GET /gantry/consultation/<id>`. |
| **Optional** | FastAPI + WebSocket | `src/main_fastapi.py` + `fleet_v2` for async/real-time; skills in `src/skills/`. |

---

## High-Level Architecture

```mermaid
flowchart TB
    subgraph External["External Layer"]
        WebUI["Web UI (Chat)"]
        Voice["Voice / Siri (iOS Shortcuts)"]
        API["REST API"]
    end

    subgraph Tunnel["Cloudflare Tunnel (optional)"]
        Uplink["gantry_uplink"]
    end

    subgraph FlaskApp["Flask API (V6.5)"]
        Auth["Session Auth<br/>Rate Limit"]
        Guard["Guardrails<br/>Content Filter"]
        Endpoints["Endpoints:<br/>/voice, /consult, /architect"]
    end

    subgraph Consultation["Consultation Loop"]
        Consultant["CTO Consultant<br/>consultant.py"]
        DB_Conv["DB: conversation_history<br/>design_target, pending_question"]
    end

    subgraph Brain["AI Architect (Bedrock)"]
        Claude["Claude 3.5 Sonnet"]
        Themes["FAMOUS_THEMES<br/>Clone mode"]
    end

    subgraph Security["Security Layer"]
        Policy["Policy Gate<br/>Forbidden Patterns"]
        Proxy["Docker Proxy<br/>tcp://docker-proxy:2375"]
    end

    subgraph Foundry["Foundry (Docker)"]
        Pod["Project Pod<br/>Ephemeral"]
        DMS["Dead Man's Switch<br/>180s Timeout"]
        Limits["Resource Limits<br/>512MB RAM"]
    end

    subgraph Deploy["Deployment"]
        Vercel["Deployer<br/>Vercel CLI"]
        GitHub["Publisher<br/>GitHub PR"]
        BB["Black Box<br/>Evidence"]
    end

    subgraph Storage["Storage"]
        DB[(PostgreSQL<br/>missions, consultation)]
        Missions["missions/<br/>design-reference image"]
    end

    External --> Tunnel
    Tunnel --> FlaskApp
    FlaskApp --> Consultation
    Consultation --> DB_Conv
    Consultation --> Brain
    Brain --> Security --> Foundry
    Foundry --> Deploy
    FlaskApp --> DB
    BB --> Missions
    Missions -.->|"injected into pod"| Foundry
```

---

## Core Components

| Component | Role |
|-----------|------|
| **Flask API** (`src/main.py`) | Serves Web UI, `/gantry/auth`, `/gantry/voice`, `/gantry/consult`, `/gantry/consultation/<id>`, `/gantry/themes`, `/gantry/architect`, `/gantry/status/<id>`, etc. |
| **CTO Consultant** (`src/core/consultant.py`) | Analyzes user message and conversation history; returns proposal, clarifying question, or `ready_to_build` with design_target. |
| **Fleet Manager** (`src/core/fleet.py`) | `process_voice_input()`: start/continue consultation, save design image, call Consultant; on confirm, `_dispatch_build()` → Architect → Policy → Foundry → Deploy → Publish. |
| **Architect** (`src/core/architect.py`) | Drafts blueprint (GantryManifest); supports `design_target` (FAMOUS_THEMES) for clone mode. |
| **Foundry** (`src/core/foundry.py`) | Runs build in Docker; injects `missions/{id}/design-reference.*` into pod as `public/design-reference.*`. |
| **Policy** (`src/core/policy.py`) | Validates manifest (forbidden patterns, stack, limits). |
| **DB** (`src/core/db.py`) | Missions, conversation_history, design_target, pending_question, proposed_stack. |

---

## Interaction Flow Diagrams

### Consultation Flow (Primary: Voice / Chat)

This is the main V6.5 path: **Voice/Chat → CTO Proposal → User Feedback → “Proceed” → Build.**

```mermaid
sequenceDiagram
    participant User as User
    participant API as Flask API
    participant Fleet as Fleet Manager
    participant Consultant as CTO Consultant
    participant DB as Database
    participant Architect as Architect
    participant Pod as Foundry / Pod
    participant Vercel as Vercel
    participant GitHub as GitHub

    rect rgb(240, 248, 255)
        Note over User,Consultant: Phase 1: Consultation (multi-turn)
        User->>API: POST /gantry/voice or /gantry/consult<br/>{message, optional image_base64}
        API->>Fleet: process_voice_input(message, image_*=...)
        Fleet->>DB: create_consultation / get_active_consultation
        Fleet->>Fleet: _save_design_image(mission_id, image) → missions/{id}/design-reference.*
        Fleet->>Consultant: run(conversation_history, message)
        Consultant-->>Fleet: ConsultantResponse (question OR ready_to_build, design_target)
        Fleet->>DB: append_to_conversation, set_pending_question / mark_ready_to_build
        Fleet-->>API: {status: "AWAITING_INPUT", speech, question, ...}
        API-->>User: 200 + response (TTS speech, question)
    end

    User->>API: "Yes, proceed" (or confirm)
    API->>Fleet: process_voice_input("yes, proceed")
    Fleet->>Consultant: run(...)
    Consultant-->>Fleet: ready_to_build=true, design_target, build_prompt
    Fleet->>Fleet: _dispatch_build()

    rect rgb(255, 248, 240)
        Note over Fleet,GitHub: Phase 2: Build pipeline
        Fleet->>Architect: draft_blueprint(prompt, design_target=...)
        Architect-->>Fleet: GantryManifest
        Fleet->>Pod: Build + audit (self-heal up to 3)
        Pod-->>Fleet: Audit passed
        Fleet->>Vercel: Deploy
        Vercel-->>Fleet: Live URL
        Fleet->>GitHub: Open PR
        GitHub-->>Fleet: PR URL
        Fleet->>DB: update_mission_status(DEPLOYED / SUCCESS)
    end

    User->>API: GET /gantry/status/{mission_id}
    API-->>User: {status, url, pr_url, speech}
```

### Direct Build (Legacy / Bypass Consultation)

Single-shot build without the consultation loop (e.g. automation or “build exactly this”).

```mermaid
sequenceDiagram
    participant Client as Client
    participant API as Flask API
    participant Fleet as Fleet Manager
    participant Architect as Architect
    participant Pod as Foundry
    participant Vercel as Vercel
    participant GitHub as GitHub

    Client->>API: POST /gantry/architect<br/>{voice_memo, deploy, publish}
    API->>API: Auth + rate limit
    API->>Fleet: dispatch_mission(voice_memo, deploy, publish)
    Fleet-->>API: mission_id
    API-->>Client: 202 {mission_id, speech: "Gantry assumes control."}

    Note over Fleet,GitHub: Background thread
    Fleet->>Architect: draft_blueprint(voice_memo)
    Architect-->>Fleet: GantryManifest
    Fleet->>Pod: Build + audit (self-heal up to 3)
    Pod-->>Fleet: Success
    Fleet->>Vercel: Deploy
    Fleet->>GitHub: Open PR

    Client->>API: GET /gantry/status/{id} or GET /gantry/latest
    API-->>Client: {status, url, pr_url, speech}
```

### Design Image Flow

Optional image attached to a consultation is stored and then included in the built repo.

```mermaid
flowchart LR
    A[User uploads image<br/>in Web UI] --> B[POST /gantry/voice or /consult<br/>image_base64, image_filename]
    B --> C[Fleet: _save_design_image]
    C --> D["missions/{mission_id}/<br/>design-reference.png"]
    D --> E[Foundry: build]
    E --> F["Tar includes file as<br/>public/design-reference.png"]
    F --> G[Project Pod / Repo]
```

---

## Data Models

### Mission (DB)

Relevant fields for V6.5:

- `id`, `status`, `prompt`, `speech_output`
- `conversation_history` (JSONB): list of {role, content}
- `design_target` (e.g. "LINKEDIN", "TWITTER") for clone mode
- `pending_question`, `proposed_stack`
- Created via `create_consultation` / `create_mission`; updated by `append_to_conversation`, `set_design_target`, `mark_ready_to_build`, etc.

### ConsultantResponse (Consultant)

- `response`: natural language reply
- `status`: `NEEDS_INPUT` | `NEEDS_CONFIRMATION` | `READY_TO_BUILD`
- `question`: optional clarifying question
- `design_target`, `proposed_stack`, `build_prompt`, `features`, `confidence`

### GantryManifest (Architect)

- `project_name`, `stack`, `files`, `audit_command`, `run_command`

---

## Security Architecture

- **Edge**: Cloudflare Tunnel (optional): DDoS, WAF.
- **API**: Flask + session auth (password, SHA256 or env hash), rate limiting, guardrails.
- **Policy Gate**: Forbidden patterns, stack whitelist, file limits (`policy.yaml`).
- **Docker**: No direct socket access; use Docker proxy (`tcp://docker-proxy:2375`).
- **Pod**: Ephemeral, 512MB limit, 180s Dead Man’s Switch.

---

## Optional: FastAPI and Skills

The repo also includes an **optional** FastAPI-based stack:

- **API**: `src/main_fastapi.py` (async, WebSocket for real-time status).
- **Fleet**: `src/core/fleet_v2.py` (WebSocket broadcast).
- **Auth**: `src/core/auth_v2.py` (e.g. Argon2, TokenBucket).
- **Skills**: `src/skills/` (e.g. `consult` skill) for pluggable capabilities.

The **primary production path** is Flask + Consultant + Fleet (`src/main.py` + `src/core/fleet.py` + `src/core/consultant.py`). Use FastAPI/skills when you need async and real-time updates.

---

## Extension Points

- **New famous-app theme**: Add an entry to `FAMOUS_THEMES` in `src/core/architect.py` and expose via `GET /gantry/themes`.
- **Consultation behavior**: Adjust CTO system prompt and response parsing in `src/core/consultant.py`.
- **New stack or policy**: Update `policy.yaml`, `StackType`, and Foundry/Architect as needed.

---

*Last updated: January 2026 (V6.5)*
