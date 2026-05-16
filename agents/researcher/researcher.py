from __future__ import annotations

import json
import logging
from typing import Any

from shared.config.settings import settings
from tools.github.client import GitHubClientError, GitHubReadOnlyClient
from tools.search.client import SearchClientError, TavilySearchClient


logger = logging.getLogger(__name__)


class ResearcherAgent:
    """Researches incident context using read-only tools when configured."""

    DEFAULT_FILE_PATHS = [
        "README.md",
        "Dockerfile",
        "docker-compose.yml",
        "pyproject.toml",
        "apps/api/main.py",
        "shared/config/settings.py",
    ]

    async def research(self, query: str) -> dict[str, Any]:
        logger.info("ResearcherAgent researching query: %s", query)
        result: dict[str, Any] = {
            "summary": f"Stub research result for: {query}",
            "web_search": None,
            "github_context": None,
            "github_files": [],
            "errors": [],
        }
        incident = self._parse_incident(query)
        search_client = TavilySearchClient()
        search_query = self._build_search_query(incident, query)
        if search_client.configured:
            try:
                result["web_search"] = await search_client.search(search_query)
            except SearchClientError as exc:
                result["errors"].append(f"Web search failed: {exc}")
        else:
            result["errors"].append("Web search skipped: TAVILY_API_KEY is not configured.")

        repository = self._extract_repository(query)
        if not repository:
            return result

        github_client = GitHubReadOnlyClient()
        if not github_client.configured:
            logger.info("Skipping GitHub enrichment because GITHUB_TOKEN is not configured")
            result["errors"].append("GitHub enrichment skipped: GITHUB_TOKEN is not configured.")
            return result

        try:
            result["github_context"] = await github_client.summarize_repository_context(repository)
        except GitHubClientError as exc:
            logger.warning("GitHub enrichment failed for %s: %s", repository, exc)
            result["errors"].append(f"GitHub enrichment failed for {repository}: {exc}")

        file_paths = self._extract_file_paths(incident)
        try:
            result["github_files"] = await github_client.read_repository_files(
                repository=repository,
                paths=file_paths,
            )
        except GitHubClientError as exc:
            logger.warning("GitHub file inspection failed for %s: %s", repository, exc)
            result["errors"].append(f"GitHub file inspection failed for {repository}: {exc}")

        return result

    def format_for_prompt(self, research_result: dict[str, Any]) -> str:
        sections = [str(research_result.get("summary", ""))]

        github_context = research_result.get("github_context")
        if github_context:
            sections.append(
                "GitHub repository context:\n"
                f"{json.dumps(github_context, indent=2, default=str)}"
            )

        web_search = research_result.get("web_search")
        if web_search:
            sections.append(
                "Live web search results:\n"
                f"{json.dumps(web_search, indent=2, default=str)}"
            )

        github_files = research_result.get("github_files") or []
        readable_files = [
            {
                "path": file.get("path"),
                "size": file.get("size"),
                "truncated": file.get("truncated"),
                "content": file.get("content"),
            }
            for file in github_files
            if file.get("ok")
        ]
        if readable_files:
            sections.append(
                "GitHub file snippets:\n"
                f"{json.dumps(readable_files, indent=2, default=str)}"
            )

        errors = research_result.get("errors") or []
        if errors:
            sections.append(
                "Research warnings:\n"
                + "\n".join(f"- {error}" for error in errors)
            )

        return "\n\n".join(section for section in sections if section)

    def _build_search_query(self, incident: dict[str, Any], raw_query: str) -> str:
        payload = incident.get("payload", {}) if isinstance(incident, dict) else {}
        if not isinstance(payload, dict):
            return raw_query[:500]
        parts = [
            payload.get("service"),
            payload.get("severity"),
            payload.get("message"),
            payload.get("title"),
            payload.get("resource_type"),
        ]
        query = " ".join(str(part) for part in parts if part)
        if query:
            return f"SRE incident remediation {query}"[:500]
        return raw_query[:500]

    def _parse_incident(self, query: str) -> dict[str, Any]:
        try:
            incident = json.loads(query)
        except json.JSONDecodeError:
            return {}
        return incident if isinstance(incident, dict) else {}

    def _extract_repository(self, query: str) -> str | None:
        incident = self._parse_incident(query)

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

    def _extract_file_paths(self, incident: dict[str, Any]) -> list[str]:
        payload = incident.get("payload", {}) if isinstance(incident, dict) else {}
        requested_paths = []
        if isinstance(payload, dict):
            requested_paths = (
                payload.get("files")
                or payload.get("file_paths")
                or payload.get("paths")
                or []
            )

        if isinstance(requested_paths, str):
            requested_paths = [requested_paths]
        if not isinstance(requested_paths, list):
            requested_paths = []

        paths = [str(path) for path in requested_paths if path]
        if not paths:
            paths = self.DEFAULT_FILE_PATHS.copy()

        return self._dedupe_and_limit_paths(paths)

    def _dedupe_and_limit_paths(self, paths: list[str], limit: int = 8) -> list[str]:
        seen = set()
        safe_paths = []
        for path in paths:
            normalized = path.strip().replace("\\", "/").lstrip("/")
            if not normalized or normalized in seen:
                continue
            if ".." in normalized.split("/"):
                continue
            seen.add(normalized)
            safe_paths.append(normalized)
            if len(safe_paths) >= limit:
                break
        return safe_paths
