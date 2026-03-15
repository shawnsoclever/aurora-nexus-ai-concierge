from __future__ import annotations

import re

from guardrails.models import GuardrailDecision


SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore\s+all\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"developer\s+message", re.IGNORECASE),
]


def evaluate_input(text: str, correlation_id: str) -> GuardrailDecision:
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            return GuardrailDecision(
                correlation_id=correlation_id,
                stage="input",
                decision="block",
                reason_code="PROMPT_INJECTION_DETECTED",
                message="Input violates prompt safety policy.",
            )

    return GuardrailDecision(
        correlation_id=correlation_id,
        stage="input",
        decision="allow",
        reason_code="INPUT_SAFE",
        message="Input is allowed.",
    )
