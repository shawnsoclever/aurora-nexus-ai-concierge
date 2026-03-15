from __future__ import annotations

from guardrails.models import GuardrailDecision

from agents.policies import ROLE_TOOL_ALLOWLIST


SENSITIVE_INTENTS = {"booking", "payment", "complaint"}


def evaluate_policy(
    *,
    correlation_id: str,
    agent_name: str,
    intended_tool: str | None,
    intent: str,
) -> GuardrailDecision:
    if intent in SENSITIVE_INTENTS and not intended_tool:
        return GuardrailDecision(
            correlation_id=correlation_id,
            stage="policy",
            decision="block",
            reason_code="SENSITIVE_OPERATION_WITHOUT_TOOL",
            message="Sensitive operation must be bound to an approved tool path.",
        )

    if intended_tool:
        allowed_tools = ROLE_TOOL_ALLOWLIST.get(agent_name, set())
        if intended_tool not in allowed_tools:
            return GuardrailDecision(
                correlation_id=correlation_id,
                stage="policy",
                decision="block",
                reason_code="TOOL_NOT_ALLOWED_FOR_AGENT",
                message=f"Tool '{intended_tool}' is not allowed for {agent_name}.",
            )

    return GuardrailDecision(
        correlation_id=correlation_id,
        stage="policy",
        decision="allow",
        reason_code="POLICY_OK",
        message="Policy checks passed.",
    )
