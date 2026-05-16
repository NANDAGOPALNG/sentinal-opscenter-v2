# Sentinal OpsCenter V2

Autonomous multi-agent SRE workflow platform built with FastAPI, LangGraph, Groq, SQLite, and read-only GitHub tooling.

## What It Does

Sentinal accepts incident/webhook events, normalizes the payload, runs a multi-agent workflow, persists the full execution state, and exposes API endpoints for inspection.

Current workflow:

1. Planner creates an incident response plan with Groq.
2. Researcher gathers stub research plus optional read-only GitHub repository context.
3. Fixer drafts a safe remediation proposal with Groq.
4. Validator checks that the proposal is actionable and includes investigation, validation, and safety/rollback language.
5. Notifier records lifecycle notifications and optionally posts to Discord.
6. Workflow state is persisted in SQLite.

## Implemented Features

- FastAPI service with `/health`
- Async LangGraph incident workflow
- SQLite persistence with async SQLAlchemy
- Full workflow detail persistence:
  - plan
  - findings
  - GitHub context
  - inspected GitHub files
  - fix proposal
  - validation report
  - notifications
  - trace id
- Read-only GitHub client:
  - token validation
  - repository summary
  - recent issues
  - recent pull requests
  - safe file snippets
- GitHub webhook/event normalization
- Tavily live web search when `TAVILY_API_KEY` is configured
- Optional GitHub webhook signature verification
- Webhook idempotency with `X-GitHub-Delivery` or explicit `idempotency_key`
- Docker and docker-compose support

## Project Structure

```text
apps/api/                  FastAPI app, DB setup, workflow executor
agents/planner/            Groq-backed planner agent
agents/researcher/         Stub research plus GitHub context/file inspection
agents/fixer/              Groq-backed fix proposal agent
agents/validator/          Local proposal validator
agents/notifier/           Log/Discord lifecycle notifications
shared/config/             Settings
shared/models/             SQLAlchemy models
shared/schemas/            Pydantic workflow state
shared/utils/              Event normalization, idempotency, webhook security
tools/github/              Read-only GitHub client
workflows/                 LangGraph workflow
```

## Setup

Copy the example environment file and fill in keys:

```powershell
Copy-Item .env.example .env
```

Minimum required:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Recommended optional values:

```env
GITHUB_TOKEN=your_github_token_here
GITHUB_REPOSITORY=NANDAGOPALNG/sentinal-opscenter-v2
```

If `GITHUB_WEBHOOK_SECRET` is set, `/webhook` and `/webhook/preview` require a valid `X-Hub-Signature-256` header.

## Run

```powershell
docker-compose up --build
```

API runs on:

```text
http://localhost:8001
```

Run the Streamlit dashboard:

```powershell
uv run streamlit run apps/dashboard/streamlit_app.py
```

Dashboard URL:

```text
http://localhost:8501
```

Health check:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/health"
```

## Demo Commands

Fast smoke test:

```powershell
.\scripts\smoke-test.ps1
```

If `GITHUB_WEBHOOK_SECRET` is set only in `.env`, pass it explicitly:

```powershell
.\scripts\smoke-test.ps1 -WebhookSecret "your_secret_here"
```

Create a test incident:

```powershell
$body = @{
  event_type = "test_incident"
  service = "api"
  severity = "warning"
  message = "Synthetic latency spike with GitHub file context"
  repository = "NANDAGOPALNG/sentinal-opscenter-v2"
  files = @("README.md", "Dockerfile", "docker-compose.yml", "apps/api/main.py")
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8001/webhook" -Method Post -ContentType "application/json" -Body $body
```

List workflows:

```powershell
$workflows = Invoke-RestMethod -Uri "http://localhost:8001/workflows"
$workflows
```

Inspect latest workflow:

```powershell
$newId = $workflows[0].id
$workflow = Invoke-RestMethod -Uri "http://localhost:8001/workflows/$newId"
$workflow
```

Inspect persisted agent outputs:

```powershell
$workflow.findings.github_context
$workflow.findings.github_files
$workflow.findings.validation
$workflow.findings.notifications
```

## GitHub Endpoints

Check GitHub authentication and webhook security status:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/github/status"
```

Fetch read-only repository context:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/github/context?repository=NANDAGOPALNG/sentinal-opscenter-v2"
```

Preview webhook normalization without running a workflow:

```powershell
$body = @{
  repository = @{
    full_name = "NANDAGOPALNG/sentinal-opscenter-v2"
  }
  ref = "refs/heads/main"
  head_commit = @{
    message = "Update API workflow"
    modified = @("apps/api/main.py", "workflows/incident_graph.py")
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8001/webhook/preview" -Method Post -ContentType "application/json" -Body $body
```

## Idempotency Demo

If `GITHUB_WEBHOOK_SECRET` is not set, you can test duplicate handling with an explicit idempotency key:

```powershell
$body = @{
  event_type = "test_incident"
  message = "Test idempotency"
  repository = "NANDAGOPALNG/sentinal-opscenter-v2"
  idempotency_key = "local-idempotency-001"
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8001/webhook" -Method Post -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "http://localhost:8001/webhook" -Method Post -ContentType "application/json" -Body $body
```

Expected:

- first request: `accepted`
- second request: `duplicate`

If `GITHUB_WEBHOOK_SECRET` is set, include a valid `X-Hub-Signature-256` header.

## Notes

- GitHub integration is currently read-only by design.
- The system does not create branches, commits, or PRs yet.
- Tavily/search and write-capable GitHub actions are reserved for later stages.
- SQLite is used for local/demo persistence.
