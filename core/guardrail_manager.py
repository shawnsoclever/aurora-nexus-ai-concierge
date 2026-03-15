from __future__ import annotations

from dataclasses import asdict

from loguru import logger

from guardrails.input_guard import evaluate_input
from guardrails.models import GuardrailDecision
from guardrails.output_guard import sanitize_output
from guardrails.policy_guard import evaluate_policy
from guardrails.tool_guard import evaluate_tool_call


class GuardrailManager:
    def __init__(self) -> None:
        self._log = logger.bind(component="guardrail")

    def _record(self, decision: GuardrailDecision) -> GuardrailDecision:
        self._log.info("guardrail_decision={payload}", payload=asdict(decision))
        return decision

    def check_input(self, *, correlation_id: str, text: str) -> GuardrailDecision:
        return self._record(evaluate_input(text=text, correlation_id=correlation_id))

    def check_policy(
        self,
        *,
        correlation_id: str,
        agent_name: str,
        intended_tool: str | None,
        intent: str,
    ) -> GuardrailDecision:
        return self._record(
            evaluate_policy(
                correlation_id=correlation_id,
                agent_name=agent_name,
                intended_tool=intended_tool,
                intent=intent,
            )
        )

    def check_tool(self, *, correlation_id: str, tool_name: str, payload: dict) -> GuardrailDecision:
        return self._record(
            evaluate_tool_call(correlation_id=correlation_id, tool_name=tool_name, payload=payload)
        )

    def check_output(self, *, correlation_id: str, text: str) -> tuple[str, GuardrailDecision]:
        sanitized, decision = sanitize_output(correlation_id=correlation_id, text=text)
        return sanitized, self._record(decision)
