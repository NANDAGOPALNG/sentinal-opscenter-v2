from __future__ import annotations

import logging

from langchain_groq import ChatGroq

from shared.config.settings import settings


logger = logging.getLogger(__name__)


class FixerAgent:
    """Creates a safe remediation suggestion from incident context and research."""

    def __init__(self) -> None:
        self.llm = ChatGroq(
            groq_api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0.2,
        )

    async def propose_fix(self, incident: str, research: str) -> str:
        logger.info("FixerAgent proposing fix")
        prompt = (
            "You are the fixer agent in an autonomous SRE workflow. "
            "Draft a concise, safe remediation proposal. Do not claim to have made "
            "external changes, opened PRs, or contacted services.\n\n"
            f"Incident:\n{incident}\n\n"
            f"Research:\n{research}"
        )
        response = await self.llm.ainvoke(prompt)
        return str(getattr(response, "content", response)).strip()
