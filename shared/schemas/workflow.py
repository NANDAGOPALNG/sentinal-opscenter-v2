from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowState(BaseModel):
    """State carried through the incident response LangGraph workflow."""

    incident_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    plan: list[str] = Field(default_factory=list)
    current_step: str | None = None
    findings: dict[str, Any] = Field(default_factory=dict)
    fix_proposal: str | None = None
    validation_passed: bool = False
    retry_count: int = 0
    max_retries: int = 2
    status: str = "created"
    error: str | None = None
    pr_url: str | None = None
    trace_id: str | None = None
    dedupe_key: str | None = None
