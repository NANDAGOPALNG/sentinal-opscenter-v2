import logging
import asyncio
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db.database import AsyncSessionLocal, init_db
from apps.api.services.workflow_executor import run_incident_workflow
from shared.config.settings import settings
from shared.models.incident import IncidentWorkflow
from tools.github.client import GitHubClientError, GitHubReadOnlyClient

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


@app.get("/health")
async def health():
    return {"status": "alive", "version": "v2"}


@app.post("/webhook")
async def webhook(event: dict[str, Any]):
    event_type = str(event.get("event_type") or event.get("type") or "unknown")
    logger.info("Webhook received: event_type=%s payload=%s", event_type, event)
    asyncio.create_task(run_incident_workflow(event_type, event))
    return {"status": "accepted"}


@app.get("/workflows")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(IncidentWorkflow)
        .order_by(IncidentWorkflow.created_at.desc())
        .limit(10)
    )
    workflows = result.scalars().all()
    return [
        {
            "id": workflow.id,
            "status": workflow.status,
            "event_type": workflow.event_type,
            "created_at": workflow.created_at,
        }
        for workflow in workflows
    ]


@app.get("/workflows/{incident_id}")
async def get_workflow(incident_id: str, db: AsyncSession = Depends(get_db)):
    workflow = await db.get(IncidentWorkflow, incident_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "id": workflow.id,
        "event_type": workflow.event_type,
        "payload": workflow.payload,
        "status": workflow.status,
        "plan": workflow.plan,
        "current_step": workflow.current_step,
        "findings": workflow.findings,
        "fix_proposal": workflow.fix_proposal,
        "validation_passed": workflow.validation_passed,
        "retry_count": workflow.retry_count,
        "max_retries": workflow.max_retries,
        "error": workflow.error,
        "pr_url": workflow.pr_url,
        "trace_id": workflow.trace_id,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }


@app.get("/github/status")
async def github_status():
    github_client = GitHubReadOnlyClient()
    try:
        return await github_client.validate_token()
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/github/context")
async def github_context(
    repository: str = Query(
        default="",
        description="Repository full name, for example 'owner/name'. Uses GITHUB_REPOSITORY if omitted.",
    )
):
    repository_name = repository or settings.github_repository
    if not repository_name:
        raise HTTPException(
            status_code=400,
            detail="Provide repository query param or set GITHUB_REPOSITORY",
        )

    github_client = GitHubReadOnlyClient()
    try:
        return await github_client.summarize_repository_context(repository_name)
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
