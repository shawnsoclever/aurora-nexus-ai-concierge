from __future__ import annotations

from guardrails.models import GuardrailDecision


def evaluate_tool_call(
    *,
    correlation_id: str,
    tool_name: str,
    payload: dict,
) -> GuardrailDecision:
    if "payment" in tool_name and float(payload.get("amount", 0)) <= 0:
        return GuardrailDecision(
            correlation_id=correlation_id,
            stage="tool",
            decision="block",
            reason_code="INVALID_PAYMENT_AMOUNT",
            message="Payment amount must be greater than zero.",
        )

    if "booking" in tool_name:
        checkin = payload.get("checkin_date", "")
        checkout = payload.get("checkout_date", "")
        if checkin and checkout and checkin >= checkout:
            return GuardrailDecision(
                correlation_id=correlation_id,
                stage="tool",
                decision="block",
                reason_code="INVALID_BOOKING_DATES",
                message="checkout_date must be after checkin_date.",
            )

    return GuardrailDecision(
        correlation_id=correlation_id,
        stage="tool",
        decision="allow",
        reason_code="TOOL_CALL_SAFE",
        message="Tool call is allowed.",
    )
