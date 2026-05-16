from __future__ import annotations

import json
import logging

from shared.config.settings import settings
from tools.github.client import GitHubClientError, GitHubReadOnlyClient


logger = logging.getLogger(__name__)


class ResearcherAgent:
    """Researches incident context using read-only tools when configured."""

    async def research(self, query: str) -> str:
        logger.info("ResearcherAgent researching query: %s", query)
        result = f"Stub research result for: {query}"
        repository = self._extract_repository(query)
        if not repository:
            return result

        github_client = GitHubReadOnlyClient()
        if not github_client.configured:
            logger.info("Skipping GitHub enrichment because GITHUB_TOKEN is not configured")
            return f"{result}\n\nGitHub enrichment skipped: GITHUB_TOKEN is not configured."

        try:
            context = await github_client.summarize_repository_context(repository)
        except GitHubClientError as exc:
            logger.warning("GitHub enrichment failed for %s: %s", repository, exc)
            return f"{result}\n\nGitHub enrichment failed for {repository}: {exc}"

        return (
            f"{result}\n\n"
            f"GitHub repository context for {repository}:\n"
            f"{json.dumps(context, indent=2, default=str)}"
        )

    def _extract_repository(self, query: str) -> str | None:
        try:
            incident = json.loads(query)
        except json.JSONDecodeError:
            return settings.github_repository or None

        payload = incident.get("payload", {}) if isinstance(incident, dict) else {}
        if not isinstance(payload, dict):
            return settings.github_repository or None

        repository = (
            payload.get("repository")
            or payload.get("repo")
            or payload.get("github_repository")
            or settings.github_repository
        )
        if isinstance(repository, dict):
            repository = repository.get("full_name")
        if repository:
            return str(repository)
        return None
