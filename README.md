# Sentinal OpsCenter V2

**Autonomous multi-agent incident response platform for Site Reliability Engineering**

Sentinal OpsCenter V2 is an agentic SRE workflow engine that ingests production incidents, orchestrates a coordinated team of AI agents through a structured response pipeline, and persists a full audit trail — from triage to remediation — in a queryable API.

---

## Overview

Modern engineering teams lose critical time in the gap between detecting an incident and executing a coordinated response. Sentinal OpsCenter V2 closes that gap by deploying a pipeline of specialized AI agents the moment an event arrives. Each agent owns a distinct responsibility: planning, research, fix proposal, validation, and notification. The agents collaborate through a stateful LangGraph workflow, and every decision is persisted to SQLite for full post-incident review.

---

## Architecture

```
Incoming Event (webhook / manual)
        |
        v
  Event Normalizer  ─────────────────────────────────────────────────────────────────────
        |                                                                                 |
        v                                                                        Idempotency
  LangGraph Workflow                                                                  Guard
        |
        +──> Planner Agent         Creates a structured incident response plan (Groq LLM)
        |
        +──> Researcher Agent      Gathers context: GitHub repo summary, file snippets,
        |                          live web search via Tavily (when configured)
        |
        +──> Fixer Agent           Drafts a safe, actionable remediation proposal (Groq LLM)
        |
        +──> Validator Agent       Verifies the proposal includes investigation steps,
        |    |                     validation criteria, and rollback/safety language
        |    |
        |    +── PASS ──> Finish Node
        |    |
        |    +── FAIL ──> Retry Node ──> Planner (up to max_retries)
        |    |
        |    +── MAX RETRIES ──> Fail Node
        |
        +──> Notifier Agent        Records lifecycle notifications; optionally posts to Discord
        |
        v
  SQLite Persistence                Full workflow state: plan, findings, GitHub context,
                                    file snippets, fix proposal, validation report,
                                    notifications, trace ID, dedupe key
```

---

## Agent Responsibilities

| Agent | Role | Backing |
|---|---|---|
| Planner | Parses the incident and produces a step-by-step response plan | Groq LLM (llama-3.3-70b-versatile) |
| Researcher | Fetches repository context, file snippets, and live web results | GitHub API (read-only) + Tavily |
| Fixer | Drafts a remediation proposal grounded in research context | Groq LLM |
| Validator | Checks the proposal for completeness, actionability, and rollback coverage | Local rule-based |
| Notifier | Records lifecycle events and posts to Discord if configured | Discord webhook |

---

## Key Features

**Workflow Engine**
- Async LangGraph state machine with conditional retry routing
- Automatic retry with feedback: failed proposals re-enter the planner with explicit guidance on what was missing
- Configurable max retry ceiling to prevent runaway loops

**Incident Ingestion**
- Accepts arbitrary JSON payloads via `/webhook`
- GitHub event normalization — raw push, pull request, and issue events are mapped to a unified incident schema
- Webhook signature verification via `X-Hub-Signature-256` when `GITHUB_WEBHOOK_SECRET` is set
- Idempotency via `X-GitHub-Delivery` header or explicit `idempotency_key` field — duplicate submissions are detected and rejected without re-executing the workflow

**GitHub Integration (Read-Only)**
- Repository summary: open issues, recent pull requests, contributor activity
- Safe file inspection: fetches specific file paths from a repository at workflow time
- Path traversal protection and configurable file limit

**Persistence**
- Full workflow state written to SQLite via async SQLAlchemy
- Queryable by workflow ID; all agent outputs stored as structured JSON fields
- Trace ID and dedupe key stored alongside results for debugging and audit

**Observability**
- `/health` endpoint for liveness probes
- `/github/status` for auth and webhook security configuration status
- `/webhook/preview` for dry-run normalization without triggering a workflow
- Streamlit dashboard for browsing workflow history

---

## Project Structure

```
sentinal-opscenter-v2/
├── agents/
│   ├── fixer/          Groq-backed remediation proposal agent
│   ├── notifier/       Lifecycle notification agent (log + Discord)
│   ├── planner/        Groq-backed incident response planner
│   ├── researcher/     GitHub context + Tavily web search agent
│   └── validator/      Local proposal validator
├── apps/
│   ├── api/
│   │   ├── db/         Async SQLAlchemy setup, CRUD operations
│   │   ├── services/   Workflow executor
│   │   └── main.py     FastAPI application, all route definitions
│   └── dashboard/      Streamlit workflow browser
├── shared/
│   ├── config/         Pydantic settings, environment variable binding
│   ├── models/         SQLAlchemy ORM models
│   ├── schemas/        Pydantic workflow state schema
│   └── utils/          Event normalizer, idempotency, webhook security
├── tools/
│   ├── github/         Read-only GitHub API client
│   └── search/         Tavily web search client
├── workflows/
│   └── incident_graph.py   LangGraph workflow definition and node wiring
├── scripts/
│   └── smoke-test.ps1  End-to-end test script
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Workflow engine | LangGraph |
| LLM | Groq (llama-3.3-70b-versatile) |
| Database | SQLite + async SQLAlchemy + aiosqlite |
| GitHub integration | PyGitHub |
| Web search | Tavily |
| Dashboard | Streamlit |
| Runtime | Python 3.12+ |
| Package manager | uv |
| Containerization | Docker + docker-compose |

---

## Setup

### 1. Clone and configure environment

```bash
cp .env.example .env
```

Open `.env` and set your keys:

```env
# Required
GROQ_API_KEY=your_groq_api_key_here

# Recommended — enables GitHub context enrichment
GITHUB_TOKEN=your_github_token_here
GITHUB_REPOSITORY=owner/repository-name

# Optional — enables live web search in the Researcher agent
TAVILY_API_KEY=your_tavily_api_key_here

# Optional — enables webhook signature verification
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Optional — enables Discord lifecycle notifications
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Only `GROQ_API_KEY` is required. All other integrations degrade gracefully when not configured.

### 2. Start with Docker

```bash
docker-compose up --build
```

The API is available at `http://localhost:8001`.

### 3. Run the Streamlit dashboard (optional)

```bash
uv run streamlit run apps/dashboard/streamlit_app.py
```

Dashboard is available at `http://localhost:8501`.

---

## API Reference

### Health

```
GET /health
```

Returns service liveness and version.

### GitHub Status

```
GET /github/status
```

Reports GitHub authentication state and webhook security configuration.

### Webhook Preview

```
POST /webhook/preview
```

Dry-runs GitHub event normalization without executing a workflow. Useful for verifying payload structure.

### Submit Incident

```
POST /webhook
```

Normalizes the incoming event, checks idempotency, and runs the full multi-agent workflow asynchronously.

**Example payload:**

```json
{
  "event_type": "latency_spike",
  "service": "api",
  "severity": "warning",
  "message": "P99 latency exceeded threshold on /checkout",
  "repository": "owner/repo-name",
  "files": ["apps/api/main.py", "workflows/incident_graph.py"]
}
```

### List Workflows

```
GET /workflows
```

Returns all persisted workflow runs ordered by creation time.

### Inspect Workflow

```
GET /workflows/{id}
```

Returns the full workflow record including plan, research findings, GitHub context, file snippets, fix proposal, validation report, notifications, trace ID, and dedupe key.

---

## Running the Smoke Test

```powershell
.\scripts\smoke-test.ps1
```

If `GITHUB_WEBHOOK_SECRET` is only in `.env` and not exported to the shell:

```powershell
.\scripts\smoke-test.ps1 -WebhookSecret "your_secret_here"
```

The smoke test submits a synthetic incident, polls for completion, and prints all persisted agent outputs.

---

## Idempotency

Sentinal deduplicates incoming events before executing the workflow. If a `X-GitHub-Delivery` header is present, it is used as the dedupe key. Otherwise, an explicit `idempotency_key` field in the request body is used.

Submitting the same event twice produces:

```
first request  → { "status": "accepted" }
second request → { "status": "duplicate" }
```

The workflow runs exactly once per unique event.

---

## Scope and Design Decisions

**Read-only GitHub integration by design.** The system inspects repository state to inform remediation proposals but does not create branches, commits, or pull requests. Write-capable actions are reserved for a future stage after the validation and safety framework is further hardened.

**Local validator.** The Validator agent uses deterministic rule-based checks rather than an additional LLM call. This keeps the validation step fast, predictable, and free of hallucination risk for safety-critical checks like rollback coverage.

**SQLite for portability.** SQLite was chosen for zero-infrastructure local and demo deployments. The async SQLAlchemy setup is compatible with PostgreSQL and can be swapped with a connection string change.

**Retry with structured feedback.** When the Validator rejects a fix proposal, the workflow does not simply retry blindly. The Retry node injects explicit guidance into the workflow state describing what was missing, and this guidance is passed to the Planner on re-entry so the next proposal has context about the previous failure.

---

## Roadmap

- Write-capable GitHub actions: branch creation, commit, pull request
- Live Tavily web search in Researcher agent (integration complete; key required)
- Production database migrations via Alembic
- Enhanced Streamlit dashboard with real-time workflow status

---

## License

MIT
