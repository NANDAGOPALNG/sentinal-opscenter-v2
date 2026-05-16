from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


class ValidatorAgent:
    """Stage 2 validator stub."""

    async def validate(self, fix_proposal: str) -> tuple[bool, str]:
        logger.info("ValidatorAgent validating fix proposal")
        return True, "OK"
