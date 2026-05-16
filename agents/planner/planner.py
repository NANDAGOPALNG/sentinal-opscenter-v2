from __future__ import annotations

import json
import logging
from typing import Any

from langchain_groq import ChatGroq

from shared.config.settings import settings


logger = logging.getLogger(__name__)


class PlannerAgent:
    """Creates a concise response plan for an incoming incident."""

    def __init__(self) -> None:
        self.llm = ChatGroq(
            groq_api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0.1,
        )

    async def create_plan(self, incident_description: str) -> dict[str, Any]:
        logger.info("PlannerAgent creating plan")
        prompt = (
            "You are the planner agent for an autonomous SRE incident workflow. "
            "Return only valid JSON with this shape: "
            '{"steps": ["step one", "step two"], "reasoning": "short reason"}. '
            "Keep the plan practical, safe, and suitable for stubbed execution.\n\n"
            f"Incident:\n{incident_description}"
        )

        response = await self.llm.ainvoke(prompt)
        content = str(getattr(response, "content", response)).strip()

        try:
            parsed = json.loads(content)
            steps = parsed.get("steps", [])
            if not isinstance(steps, list):
                raise ValueError("Planner response 'steps' must be a list")
            return {
                "steps": [str(step) for step in steps],
                "reasoning": str(parsed.get("reasoning", "")),
            }
        except Exception as exc:
            logger.warning("Planner JSON parsing failed; using fallback plan: %s", exc)
            return {
                "steps": [
                    "Summarize the incident payload",
                    "Research likely causes using available context",
                    "Draft a safe remediation proposal",
                    "Validate the proposed remediation",
                ],
                "reasoning": content or "Fallback plan generated because LLM output was not valid JSON.",
            }
