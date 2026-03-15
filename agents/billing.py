from google.adk.agents import LlmAgent

from agents.common import get_model_name, get_mcp_toolset


def build_billing_agent() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="billing_agent",
        description="Handles payment processing intents and billing summaries.",
        instruction=(
            "Handle payment workflows with strict verification and clear communication. "
            "Always validate the payable amount against active booking context before charging. "
            "Present an understandable payment summary, then record the payment using allowed MCP tools. "
            "If any mismatch exists (amount, booking id, guest context, or stage), block payment and "
            "explain the exact issue to resolve."
        ),
        tools=[get_mcp_toolset()],
    )
