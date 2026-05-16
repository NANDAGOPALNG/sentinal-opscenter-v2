import logging
import asyncio
import json
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.notifier.notifier import NotifierAgent
from apps.api.db.crud import create_workflow, get_workflow_by_dedupe_key
from apps.api.db.database import AsyncSessionLocal, init_db
from apps.api.services.workflow_executor import run_incident_workflow
from shared.config.settings import settings
from shared.models.incident import IncidentWorkflow
from shared.schemas.workflow import WorkflowState
from shared.utils.event_normalizer import normalize_event
from shared.utils.idempotency import build_dedupe_key
from shared.utils.webhook_security import verify_github_signature
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


async def parse_verified_webhook_body(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    body = await request.body()
    if settings.github_webhook_secret and not verify_github_signature(
        body=body,
        signature_header=x_hub_signature_256,
        secret=settings.github_webhook_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object")
    if x_github_delivery:
        event["github_delivery_id"] = x_github_delivery
    if x_github_event:
        event["github_event_header"] = x_github_event
    return event


@app.post("/webhook")
async def webhook(
    event: dict[str, Any] = Depends(parse_verified_webhook_body),
    db: AsyncSession = Depends(get_db),
):
    event_type, normalized_payload = normalize_event(event)
    dedupe_key = build_dedupe_key(
        event_type=event_type,
        payload=normalized_payload,
        delivery_id=event.get("github_delivery_id"),
    ) or None

    existing_workflow = await get_workflow_by_dedupe_key(db, dedupe_key)
    if existing_workflow is not None:
        logger.info(
            "Duplicate webhook ignored: dedupe_key=%s workflow=%s",
            dedupe_key,
            existing_workflow.id,
        )
        return {
            "status": "duplicate",
            "event_type": event_type,
            "workflow_id": existing_workflow.id,
            "dedupe_key": dedupe_key,
        }

    if dedupe_key:
        normalized_payload["dedupe_key"] = dedupe_key
    incident_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    initial_state = WorkflowState(
        incident_id=incident_id,
        event_type=event_type,
        payload=normalized_payload,
        status="accepted",
        trace_id=trace_id,
        dedupe_key=dedupe_key,
    )
    reserved_workflow = await create_workflow(db, initial_state)
    if reserved_workflow.id != incident_id:
        return {
            "status": "duplicate",
            "event_type": event_type,
            "workflow_id": reserved_workflow.id,
            "dedupe_key": dedupe_key,
        }

    logger.info("Webhook received: event_type=%s payload=%s", event_type, normalized_payload)
    asyncio.create_task(
        run_incident_workflow(
            event_type=event_type,
            payload=normalized_payload,
            dedupe_key=dedupe_key,
            incident_id=incident_id,
            trace_id=trace_id,
            persist_initial_state=False,
        )
    )
    return {
        "status": "accepted",
        "event_type": event_type,
        "workflow_id": reserved_workflow.id,
        "dedupe_key": dedupe_key,
    }


@app.post("/webhook/preview")
async def webhook_preview(event: dict[str, Any] = Depends(parse_verified_webhook_body)):
    event_type, normalized_payload = normalize_event(event)
    dedupe_key = build_dedupe_key(
        event_type=event_type,
        payload=normalized_payload,
        delivery_id=event.get("github_delivery_id"),
    ) or None
    return {
        "event_type": event_type,
        "dedupe_key": dedupe_key,
        "payload": normalized_payload,
    }


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
            "dedupe_key": workflow.dedupe_key,
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
        "dedupe_key": workflow.dedupe_key,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }


@app.get("/github/status")
async def github_status():
    github_client = GitHubReadOnlyClient()
    try:
        status = await github_client.validate_token()
    except GitHubClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    status["webhook_secret_configured"] = bool(settings.github_webhook_secret)
    return status


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


@app.get("/notifications/status")
async def notifications_status():
    notifier = NotifierAgent()
    return {
        "discord_configured": notifier.configured,
        "default_channel": "discord" if notifier.configured else "log",
    }
