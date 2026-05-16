from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from shared.config.settings import settings
from shared.schemas.workflow import WorkflowState


logger = logging.getLogger(__name__)


class NotifierAgent:
    """Sends workflow lifecycle notifications.

    Discord is optional. When DISCORD_WEBHOOK_URL is not configured, the agent
    records a local no-op notification so workflows remain fully runnable.
    """

    def __init__(self, discord_webhook_url: str | None = None) -> None:
        self.discord_webhook_url = (
            settings.discord_webhook_url
            if discord_webhook_url is None
            else discord_webhook_url
        )

    @property
    def configured(self) -> bool:
        return bool(self.discord_webhook_url)

    async def notify_started(self, state: WorkflowState) -> dict[str, Any]:
        return await self._notify(
            state=state,
            phase="started",
            title="Sentinal workflow started",
            description=(
                f"Incident `{state.incident_id}` started for "
                f"`{state.event_type}`."
            ),
        )

    async def notify_finished(self, state: WorkflowState) -> dict[str, Any]:
        title = "Sentinal workflow completed"
        if state.status == "failed":
            title = "Sentinal workflow failed"

        return await self._notify(
            state=state,
            phase=state.status,
            title=title,
            description=(
                f"Incident `{state.incident_id}` finished with "
                f"status `{state.status}`."
            ),
        )

    async def _notify(
        self,
        state: WorkflowState,
        phase: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        notification = {
            "channel": "discord" if self.configured else "log",
            "phase": phase,
            "status": "skipped" if not self.configured else "pending",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }

        if not self.configured:
            logger.info("%s: %s", title, description)
            notification["reason"] = "DISCORD_WEBHOOK_URL is not configured"
            return notification

        payload = self._build_discord_payload(state, title, description)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.discord_webhook_url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Discord notification failed for %s: %s", state.incident_id, exc)
            notification["status"] = "failed"
            notification["error"] = str(exc)
            return notification

        notification["status"] = "sent"
        return notification

    def _build_discord_payload(
        self,
        state: WorkflowState,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        color = 0x2ECC71 if state.status == "completed" else 0xE67E22
        if state.status == "failed":
            color = 0xE74C3C

        fields = [
            {"name": "Incident", "value": state.incident_id, "inline": False},
            {"name": "Event Type", "value": state.event_type, "inline": True},
            {"name": "Status", "value": state.status, "inline": True},
            {"name": "Trace ID", "value": state.trace_id or "n/a", "inline": False},
        ]
        if state.error:
            fields.append({"name": "Error", "value": state.error[:1000], "inline": False})

        return {
            "username": "Sentinal OpsCenter",
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": color,
                    "fields": fields,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
