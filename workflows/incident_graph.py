from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from agents.fixer.fixer import FixerAgent
from agents.planner.planner import PlannerAgent
from agents.researcher.researcher import ResearcherAgent
from agents.validator.validator import ValidatorAgent
from shared.schemas.workflow import WorkflowState


logger = logging.getLogger(__name__)


def _state_from(value: WorkflowState | dict[str, Any]) -> WorkflowState:
    if isinstance(value, WorkflowState):
        return value
    return WorkflowState.model_validate(value)


def _dump_state(state: WorkflowState) -> dict[str, Any]:
    return state.model_dump()


def _incident_description(state: WorkflowState) -> str:
    return json.dumps(
        {
            "incident_id": state.incident_id,
            "event_type": state.event_type,
            "payload": state.payload,
        },
        indent=2,
        default=str,
    )


async def planner_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "planner"
    logger.info("Workflow %s entering planner node", state.incident_id)

    result = await PlannerAgent().create_plan(_incident_description(state))
    state.plan = result.get("steps", [])
    state.findings["planner_reasoning"] = result.get("reasoning", "")
    state.status = "planned"
    return _dump_state(state)


async def researcher_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "researcher"
    logger.info("Workflow %s entering researcher node", state.incident_id)

    query = _incident_description(state)
    researcher = ResearcherAgent()
    research_result = await researcher.research(query)
    state.findings["research"] = research_result.get("summary", "")
    state.findings["web_search"] = research_result.get("web_search")
    state.findings["github_context"] = research_result.get("github_context")
    state.findings["github_files"] = research_result.get("github_files", [])
    state.findings["research_errors"] = research_result.get("errors", [])
    state.findings["research_prompt"] = researcher.format_for_prompt(research_result)
    state.status = "researched"
    return _dump_state(state)


async def fix_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "fixer"
    logger.info("Workflow %s entering fixer node", state.incident_id)

    research = str(state.findings.get("research_prompt") or state.findings.get("research", ""))
    state.fix_proposal = await FixerAgent().propose_fix(_incident_description(state), research)
    state.status = "fix_proposed"
    return _dump_state(state)


async def validate_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "validator"
    logger.info("Workflow %s entering validator node", state.incident_id)

    passed, report = await ValidatorAgent().validate(state.fix_proposal or "")
    state.validation_passed = passed
    state.findings["validation"] = report
    state.status = "validated" if passed else "validation_failed"
    if not passed:
        state.retry_count += 1
        state.findings["last_validation_failure"] = report
    return _dump_state(state)


async def retry_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "retry"
    state.status = "retrying"
    state.findings["retry_guidance"] = (
        "Previous fix proposal failed validation. Create a more detailed proposal "
        "with explicit investigation, validation, rollback/risk language, and no "
        "claims that external changes were already applied."
    )
    logger.info(
        "Workflow %s retrying after validation failure (%s/%s)",
        state.incident_id,
        state.retry_count,
        state.max_retries,
    )
    return _dump_state(state)


async def finish_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "finish"
    state.status = "completed"
    logger.info("Workflow %s finished successfully", state.incident_id)
    return _dump_state(state)


async def fail_node(value: WorkflowState | dict[str, Any]) -> dict[str, Any]:
    state = _state_from(value)
    state.current_step = "fail"
    state.status = "failed"
    state.error = state.error or "Validation failed after maximum retries"
    logger.error("Workflow %s failed: %s", state.incident_id, state.error)
    return _dump_state(state)


def route_after_validation(value: WorkflowState | dict[str, Any]) -> str:
    state = _state_from(value)
    if state.validation_passed:
        return "finish"
    if state.retry_count < state.max_retries:
        return "retry"
    return "fail"


def build_workflow():
    workflow = StateGraph(WorkflowState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("fixer", fix_node)
    workflow.add_node("validator", validate_node)
    workflow.add_node("retry", retry_node)
    workflow.add_node("finish", finish_node)
    workflow.add_node("fail", fail_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "fixer")
    workflow.add_edge("fixer", "validator")
    workflow.add_conditional_edges(
        "validator",
        route_after_validation,
        {
            "finish": "finish",
            "retry": "retry",
            "fail": "fail",
        },
    )
    workflow.add_edge("retry", "planner")
    workflow.add_edge("finish", END)
    workflow.add_edge("fail", END)

    return workflow.compile()
