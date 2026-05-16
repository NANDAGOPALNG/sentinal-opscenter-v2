from __future__ import annotations

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
    )
    db.add(workflow)
    await db.commit()
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

    await db.commit()
    await db.refresh(workflow)
    return workflow
