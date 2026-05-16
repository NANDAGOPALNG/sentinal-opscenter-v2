from __future__ import annotations

from typing import Any


def build_dedupe_key(
    event_type: str,
    payload: dict[str, Any],
    delivery_id: str | None = None,
) -> str:
    """Build a stable idempotency key for incoming webhooks."""

    if delivery_id:
        return f"github_delivery:{delivery_id}"

    explicit_id = payload.get("event_id") or payload.get("delivery_id") or payload.get("idempotency_key")
    if explicit_id:
        return f"event:{explicit_id}"
    return ""
