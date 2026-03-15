from google.adk.agents import LlmAgent

from agents.common import get_model_name, get_mcp_toolset


def build_reservation_agent() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="reservation_agent",
        description="Creates reservations based on room availability and guest data.",
        instruction=(
            "Handle reservation intent with precision and safety. "
            "Check room availability against guest constraints, and only proceed when dates, "
            "guest count, and room selection are valid. "
            "Never bypass booking conflict checks or fabricate room availability. "
            "When a room cannot be booked, explain why and suggest the next best option. "
            "When reservation succeeds, return a concise summary suitable for payment handoff."
        ),
        tools=[get_mcp_toolset()],
    )
