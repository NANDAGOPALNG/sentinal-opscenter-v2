from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class ValidatorAgent:
    """Validates whether a proposed remediation is safe and actionable."""

    REQUIRED_SIGNALS = {
        "investigation": ["investigate", "analyze", "review", "check", "verify", "inspect"],
        "validation": ["validate", "test", "confirm", "monitor", "verify"],
        "safety": ["safe", "rollback", "risk", "impact", "avoid", "do not", "before"],
    }
    RISKY_CLAIMS = [
        "i have applied",
        "i applied",
        "i pushed",
        "i deployed",
        "opened a pr",
        "created a pull request",
        "merged",
        "deleted production",
    ]

    async def validate(self, fix_proposal: str) -> tuple[bool, dict[str, Any]]:
        logger.info("ValidatorAgent validating fix proposal")
        proposal = fix_proposal.strip()
        lower = proposal.lower()

        checks = {
            "non_empty": bool(proposal),
            "minimum_detail": len(proposal.split()) >= 40,
            "has_investigation_step": self._contains_any(lower, self.REQUIRED_SIGNALS["investigation"]),
            "has_validation_step": self._contains_any(lower, self.REQUIRED_SIGNALS["validation"]),
            "has_safety_language": self._contains_any(lower, self.REQUIRED_SIGNALS["safety"]),
            "no_risky_execution_claims": not self._contains_any(lower, self.RISKY_CLAIMS),
        }
        passed = all(checks.values())
        missing = [name for name, ok in checks.items() if not ok]

        report = {
            "status": "passed" if passed else "failed",
            "message": "Validation passed" if passed else "Validation failed",
            "checks": checks,
            "missing": missing,
        }
        return passed, report

    def _contains_any(self, text: str, needles: list[str]) -> bool:
        return any(needle in text for needle in needles)
