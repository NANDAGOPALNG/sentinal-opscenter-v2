from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.incident import IncidentWorkflow
from shared.schemas.workflow import WorkflowState


async def create_workflow(db: AsyncSession, state: WorkflowState) -> IncidentWorkflow:
    workflow = IncidentWorkflow(
        id=state.incident_id,
        event_type=state.event_type,
        payload=state.payload,
        status=state.status,
        plan=state.plan,
        current_step=state.current_step,
        findings=state.findings,
        fix_proposal=state.fix_proposal,
        validation_passed=state.validation_passed,
        retry_count=state.retry_count,
        max_retries=state.max_retries,
        error=state.error,
        pr_url=state.pr_url,
        trace_id=state.trace_id,
        dedupe_key=state.dedupe_key,
    )
    db.add(workflow)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await get_workflow_by_dedupe_key(db, state.dedupe_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(workflow)
    return workflow


async def update_workflow(db: AsyncSession, state: WorkflowState) -> IncidentWorkflow:
    workflow = await db.get(IncidentWorkflow, state.incident_id)
    if workflow is None:
        return await create_workflow(db, state)

    workflow.event_type = state.event_type
    workflow.payload = state.payload
    workflow.status = state.status
    workflow.plan = state.plan
    workflow.current_step = state.current_step
    workflow.findings = state.findings
    workflow.fix_proposal = state.fix_proposal
    workflow.validation_passed = state.validation_passed
    workflow.retry_count = state.retry_count
    workflow.max_retries = state.max_retries
    workflow.error = state.error
    workflow.pr_url = state.pr_url
    workflow.trace_id = state.trace_id
    workflow.dedupe_key = state.dedupe_key

    await db.commit()
    await db.refresh(workflow)
    return workflow


async def get_workflow_by_dedupe_key(
    db: AsyncSession,
    dedupe_key: str | None,
) -> IncidentWorkflow | None:
    if not dedupe_key:
        return None
    result = await db.execute(
        select(IncidentWorkflow).where(IncidentWorkflow.dedupe_key == dedupe_key)
    )
    return result.scalar_one_or_none()
