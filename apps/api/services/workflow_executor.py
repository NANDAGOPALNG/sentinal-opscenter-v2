from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.api.db.crud import create_workflow, update_workflow
from apps.api.db.database import AsyncSessionLocal
from shared.schemas.workflow import WorkflowState
from workflows.incident_graph import build_workflow


logger = logging.getLogger(__name__)


async def run_incident_workflow(event_type: str, payload: dict[str, Any]) -> WorkflowState:
    incident_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    state = WorkflowState(
        incident_id=incident_id,
        event_type=event_type,
        payload=payload,
        status="created",
        trace_id=trace_id,
    )

    logger.info("Starting workflow %s for event_type=%s", incident_id, event_type)

    async with AsyncSessionLocal() as db:
        await create_workflow(db, state)

    try:
        app = build_workflow()
        final_state_data = await app.ainvoke(state.model_dump())
        final_state = WorkflowState.model_validate(final_state_data)
    except Exception as exc:
        logger.exception("Workflow %s failed during execution", incident_id)
        final_state = state.model_copy(
            update={
                "status": "failed",
                "current_step": "failed",
                "error": str(exc),
            }
        )

    async with AsyncSessionLocal() as db:
        await update_workflow(db, final_state)

    logger.info("Workflow %s ended with status=%s", incident_id, final_state.status)
    return final_state
