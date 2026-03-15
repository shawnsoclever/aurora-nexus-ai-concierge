from google.adk.agents import LlmAgent

from agents.common import get_model_name, get_mcp_toolset


def build_upsell_agent() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="upsell_agent",
        description="Recommends relevant hotel services to guests.",
        instruction=(
            "Recommend premium add-on services that match the guest's purpose, group profile, "
            "and stay timeline. "
            "Use services data from MCP tools and keep recommendations selective and relevant. "
            "Prioritize usefulness over volume: suggest 2-3 strong options with a short why-it-fits rationale. "
            "Avoid irrelevant or repetitive upsells."
        ),
        tools=[get_mcp_toolset()],
    )
