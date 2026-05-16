# Submission Checklist

Use this checklist before uploading or demoing Sentinal OpsCenter V2.

## Required Files

- `README.md`
- `.env.example`
- `Dockerfile`
- `docker-compose.yml`
- `pyproject.toml`
- `uv.lock`
- `apps/`
- `agents/`
- `shared/`
- `tools/`
- `workflows/`
- `scripts/smoke-test.ps1`

Do not submit `.env`, `data/sentinal.db`, `logs/`, or `.venv/`.

## Final Local Commands

```powershell
docker-compose down
docker-compose up --build
```

In another terminal:

```powershell
.\scripts\smoke-test.ps1
```

If `GITHUB_WEBHOOK_SECRET` is set only in `.env`, pass it explicitly:

```powershell
.\scripts\smoke-test.ps1 -WebhookSecret "your_secret_here"
```

## Demo Points

- `/health` proves service is alive.
- `/github/status` proves GitHub auth and webhook security config.
- `/webhook/preview` proves GitHub event normalization.
- `/webhook` starts the LangGraph workflow.
- `/workflows` lists persisted workflow runs.
- `/workflows/{id}` shows plan, findings, GitHub context, file snippets, fix proposal, validation, notifications, trace id, and dedupe key.

## Current Scope

Implemented:

- Core FastAPI service
- Async LangGraph workflow
- Groq-backed planner and fixer
- Read-only GitHub context and file inspection
- Local validator
- Optional Discord notifications
- Optional GitHub signature verification
- Webhook idempotency
- SQLite persistence

Not implemented yet:

- Write-capable GitHub branch/PR creation
- Tavily/live web research
- Dashboard UI
- Production database migrations
