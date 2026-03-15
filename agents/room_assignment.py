from google.adk.agents import LlmAgent

from agents.common import get_model_name, get_mcp_toolset


def build_room_assignment_agent() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="room_assignment_agent",
        description="Assigns the best room based on preferences and constraints.",
        instruction=(
            "Select the most suitable room by balancing hard constraints first "
            "(availability, capacity, room type) and guest comfort preferences second "
            "(zone, noise level, floor when relevant). "
            "If a perfect match is unavailable, provide the closest viable option and explain trade-offs. "
            "Update room status only through allowed MCP tools and never modify assignment data manually."
        ),
        tools=[get_mcp_toolset()],
    )
