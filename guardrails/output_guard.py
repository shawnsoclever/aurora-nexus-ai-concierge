from __future__ import annotations

import re

from guardrails.models import GuardrailDecision


SENSITIVE_OUTPUT_PATTERNS = [
    re.compile(r"GOOGLE_API_KEY", re.IGNORECASE),
    re.compile(r"private\s+key", re.IGNORECASE),
]


def sanitize_output(*, correlation_id: str, text: str) -> tuple[str, GuardrailDecision]:
    sanitized = text
    for pattern in SENSITIVE_OUTPUT_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)

    if sanitized != text:
        decision = GuardrailDecision(
            correlation_id=correlation_id,
            stage="output",
            decision="sanitize",
            reason_code="SENSITIVE_OUTPUT_REDACTED",
            message="Sensitive output content was sanitized.",
        )
        return sanitized, decision

    decision = GuardrailDecision(
        correlation_id=correlation_id,
        stage="output",
        decision="allow",
        reason_code="OUTPUT_SAFE",
        message="Output passed safety checks.",
    )
    return sanitized, decision
