from google.adk.agents import LlmAgent

from agents.common import get_model_name, get_mcp_toolset


def build_guest_profiling_agent() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="guest_profiling_agent",
        description="Extracts and stores structured guest profile data.",
        instruction=(
            "Extract a clean guest profile from chat context: guest_type, stay_purpose, "
            "group_size, loyalty signals, and meaningful preferences. "
            "Always ensure the guest name is collected before booking preview can proceed. "
            "If name is missing, ask politely: 'May I have your name so I can prepare your reservation?'. "
            "When profile information is sufficient, store guest data using the allowed MCP tool. "
            "If data is ambiguous, ask one precise clarification instead of guessing. "
            "Keep profile summaries concise and useful for downstream room recommendation and upsell. "
            "Use warm, concise hospitality language instead of checklist-style prompts."
        ),
        tools=[get_mcp_toolset()],
    )
