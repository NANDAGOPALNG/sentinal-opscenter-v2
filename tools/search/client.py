from __future__ import annotations

import logging
from typing import Any

import httpx

from shared.config.settings import settings


logger = logging.getLogger(__name__)


class SearchClientError(RuntimeError):
    """Raised when live web search fails."""


class TavilySearchClient:
    """Small async Tavily client for live web research."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.tavily_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        if not self.configured:
            return {
                "configured": False,
                "query": query,
                "results": [],
                "answer": None,
            }

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": True,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post("https://api.tavily.com/search", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Tavily search failed: %s", exc)
            raise SearchClientError(str(exc)) from exc

        return {
            "configured": True,
            "query": query,
            "answer": data.get("answer"),
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                }
                for item in data.get("results", [])
            ],
        }
