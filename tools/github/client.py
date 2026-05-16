from __future__ import annotations

import asyncio
import logging
from itertools import islice
from typing import Any

from github import Auth, Github, GithubException

from shared.config.settings import settings


logger = logging.getLogger(__name__)


class GitHubClientError(RuntimeError):
    """Raised when a read-only GitHub operation fails."""


class GitHubReadOnlyClient:
    """Async wrapper around PyGithub for safe read-only repository context."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.github_token
        self._client = self._build_client()

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _build_client(self) -> Github | None:
        if not self.token:
            return None
        return Github(auth=Auth.Token(self.token), per_page=20)

    async def validate_token(self) -> dict[str, Any]:
        if self._client is None:
            return {"configured": False, "authenticated": False}

        def _validate() -> dict[str, Any]:
            user = self._client.get_user()
            return {
                "configured": True,
                "authenticated": True,
                "login": user.login,
            }

        return await self._run_github_call(_validate)

    async def get_repository_summary(self, repository: str) -> dict[str, Any]:
        repo = await self._get_repo(repository)
        return {
            "full_name": repo.full_name,
            "description": repo.description,
            "default_branch": repo.default_branch,
            "private": repo.private,
            "open_issues_count": repo.open_issues_count,
            "stargazers_count": repo.stargazers_count,
            "forks_count": repo.forks_count,
            "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
        }

    async def list_recent_issues(self, repository: str, limit: int = 5) -> list[dict[str, Any]]:
        repo = await self._get_repo(repository)

        def _list() -> list[dict[str, Any]]:
            issues = []
            for issue in islice(repo.get_issues(state="open", sort="updated"), limit):
                if issue.pull_request is not None:
                    continue
                issues.append(
                    {
                        "number": issue.number,
                        "title": issue.title,
                        "state": issue.state,
                        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
                        "url": issue.html_url,
                    }
                )
            return issues

        return await self._run_github_call(_list)

    async def list_recent_pull_requests(
        self,
        repository: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        repo = await self._get_repo(repository)

        def _list() -> list[dict[str, Any]]:
            pull_requests = []
            for pr in islice(repo.get_pulls(state="open", sort="updated"), limit):
                pull_requests.append(
                    {
                        "number": pr.number,
                        "title": pr.title,
                        "state": pr.state,
                        "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                        "url": pr.html_url,
                    }
                )
            return pull_requests

        return await self._run_github_call(_list)

    async def get_file_text(
        self,
        repository: str,
        path: str,
        ref: str | None = None,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        repo = await self._get_repo(repository)

        def _read() -> dict[str, Any]:
            if ref:
                content = repo.get_contents(path, ref=ref)
            else:
                content = repo.get_contents(path)
            if isinstance(content, list):
                raise GitHubClientError(f"Path is a directory, not a file: {path}")
            decoded = content.decoded_content.decode("utf-8", errors="replace")
            return {
                "path": content.path,
                "sha": content.sha,
                "size": content.size,
                "truncated": len(decoded) > max_chars,
                "content": decoded[:max_chars],
            }

        return await self._run_github_call(_read)

    async def summarize_repository_context(self, repository: str) -> dict[str, Any]:
        summary, issues, pull_requests = await asyncio.gather(
            self.get_repository_summary(repository),
            self.list_recent_issues(repository),
            self.list_recent_pull_requests(repository),
        )
        return {
            "repository": summary,
            "recent_issues": issues,
            "recent_pull_requests": pull_requests,
        }

    async def read_repository_files(
        self,
        repository: str,
        paths: list[str],
        ref: str | None = None,
        max_chars_per_file: int = 6000,
    ) -> list[dict[str, Any]]:
        results = []
        for path in paths:
            try:
                file_data = await self.get_file_text(
                    repository=repository,
                    path=path,
                    ref=ref,
                    max_chars=max_chars_per_file,
                )
                results.append({"ok": True, **file_data})
            except GitHubClientError as exc:
                results.append(
                    {
                        "ok": False,
                        "path": path,
                        "error": str(exc),
                    }
                )
        return results

    async def _get_repo(self, repository: str):
        if self._client is None:
            raise GitHubClientError("GITHUB_TOKEN is not configured")
        repository = repository.strip()
        if "/" not in repository:
            raise GitHubClientError("Repository must use the form 'owner/name'")

        def _get():
            return self._client.get_repo(repository)

        return await self._run_github_call(_get)

    async def _run_github_call(self, func):
        try:
            return await asyncio.to_thread(func)
        except GithubException as exc:
            message = exc.data.get("message") if isinstance(exc.data, dict) else str(exc)
            logger.warning("GitHub API call failed: %s", message)
            raise GitHubClientError(message) from exc
        except IndexError as exc:
            logger.warning("GitHub pagination failed: %s", exc)
            raise GitHubClientError("GitHub pagination failed while reading repository data") from exc
        except AssertionError as exc:
            logger.warning("GitHub client assertion failed: %s", exc)
            raise GitHubClientError("GitHub client rejected the repository request") from exc
