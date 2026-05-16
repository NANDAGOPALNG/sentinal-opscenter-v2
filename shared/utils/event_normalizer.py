from __future__ import annotations

from typing import Any


DEFAULT_INSPECTION_FILES = [
    "README.md",
    "Dockerfile",
    "docker-compose.yml",
    "pyproject.toml",
    "apps/api/main.py",
]


def normalize_event(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Normalize generic and GitHub webhook payloads into workflow input."""

    normalized = dict(payload)
    repository = _repository_name(payload)
    if repository:
        normalized["repository"] = repository

    if "issue" in payload:
        event_type = _github_event_type("github_issue", payload)
        issue = payload.get("issue") or {}
        normalized.update(
            {
                "source": "github",
                "resource_type": "issue",
                "title": issue.get("title"),
                "url": issue.get("html_url"),
                "number": issue.get("number"),
                "action": payload.get("action"),
                "message": _compact(
                    "GitHub issue event",
                    payload.get("action"),
                    issue.get("title"),
                ),
                "files": _files_from_payload(payload),
            }
        )
        return event_type, normalized

    if "pull_request" in payload:
        event_type = _github_event_type("github_pull_request", payload)
        pull_request = payload.get("pull_request") or {}
        normalized.update(
            {
                "source": "github",
                "resource_type": "pull_request",
                "title": pull_request.get("title"),
                "url": pull_request.get("html_url"),
                "number": pull_request.get("number"),
                "action": payload.get("action"),
                "message": _compact(
                    "GitHub pull request event",
                    payload.get("action"),
                    pull_request.get("title"),
                ),
                "files": _files_from_payload(payload),
            }
        )
        return event_type, normalized

    if "workflow_run" in payload:
        event_type = _github_event_type("github_workflow_run", payload)
        workflow_run = payload.get("workflow_run") or {}
        normalized.update(
            {
                "source": "github",
                "resource_type": "workflow_run",
                "title": workflow_run.get("name"),
                "url": workflow_run.get("html_url"),
                "action": payload.get("action"),
                "conclusion": workflow_run.get("conclusion"),
                "message": _compact(
                    "GitHub workflow run event",
                    payload.get("action"),
                    workflow_run.get("name"),
                    workflow_run.get("conclusion"),
                ),
                "files": _files_from_payload(payload),
            }
        )
        return event_type, normalized

    if "commits" in payload or "head_commit" in payload:
        event_type = _github_event_type("github_push", payload)
        normalized.update(
            {
                "source": "github",
                "resource_type": "push",
                "ref": payload.get("ref"),
                "message": _compact(
                    "GitHub push event",
                    payload.get("ref"),
                    _head_commit_message(payload),
                ),
                "files": _files_from_payload(payload),
            }
        )
        return event_type, normalized

    event_type = str(payload.get("event_type") or payload.get("type") or "unknown")
    normalized.setdefault("files", _files_from_payload(payload))
    return event_type, normalized


def _github_event_type(prefix: str, payload: dict[str, Any]) -> str:
    action = payload.get("action")
    if action:
        return f"{prefix}.{action}"
    return prefix


def _repository_name(payload: dict[str, Any]) -> str | None:
    repository = payload.get("repository") or payload.get("repo") or payload.get("github_repository")
    if isinstance(repository, dict):
        repository = repository.get("full_name")
    if repository:
        return str(repository)
    return None


def _files_from_payload(payload: dict[str, Any]) -> list[str]:
    explicit = payload.get("files") or payload.get("file_paths") or payload.get("paths")
    if explicit:
        return _normalize_paths(explicit)

    paths = []
    for commit in payload.get("commits") or []:
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified", "removed"):
            value = commit.get(key) or []
            if isinstance(value, list):
                paths.extend(value)

    head_commit = payload.get("head_commit") or {}
    if isinstance(head_commit, dict):
        for key in ("added", "modified", "removed"):
            value = head_commit.get(key) or []
            if isinstance(value, list):
                paths.extend(value)

    if not paths:
        paths = DEFAULT_INSPECTION_FILES

    return _normalize_paths(paths)


def _normalize_paths(paths: Any, limit: int = 8) -> list[str]:
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        return DEFAULT_INSPECTION_FILES.copy()

    normalized = []
    seen = set()
    for path in paths:
        candidate = str(path).strip().replace("\\", "/").lstrip("/")
        if not candidate or candidate in seen:
            continue
        if ".." in candidate.split("/"):
            continue
        seen.add(candidate)
        normalized.append(candidate)
        if len(normalized) >= limit:
            break

    return normalized or DEFAULT_INSPECTION_FILES.copy()


def _head_commit_message(payload: dict[str, Any]) -> str | None:
    head_commit = payload.get("head_commit") or {}
    if isinstance(head_commit, dict):
        return head_commit.get("message")
    return None


def _compact(*parts: Any) -> str:
    return " - ".join(str(part) for part in parts if part)
