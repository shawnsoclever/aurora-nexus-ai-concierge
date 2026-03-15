from google.adk.agents import LlmAgent

from agents.common import get_model_name, get_mcp_toolset


def build_support_agent() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="support_agent",
        description="Handles complaints and support follow-up actions.",
        instruction=(
            "Handle complaints with empathy, urgency, and operational accuracy. "
            "Capture the issue details clearly, log the complaint using allowed MCP tools, "
            "and provide practical next steps. "
            "If the issue indicates room suitability problems (noise, hygiene, AC failure, leaks, smell), "
            "attempt reassignment through reassign_room_for_complaint_tool when booking context is provided. "
            "If reassignment is unavailable, explain the fallback resolution and keep tone reassuring."
        ),
        tools=[get_mcp_toolset()],
    )
