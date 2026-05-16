from __future__ import annotations

import hashlib
import hmac


def verify_github_signature(
    body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub's X-Hub-Signature-256 header."""

    if not secret:
        return True
    if not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    supplied = signature_header[len(prefix):]
    return hmac.compare_digest(expected, supplied)
