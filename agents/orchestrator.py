from google.adk.agents import LlmAgent

from agents.billing import build_billing_agent
from agents.common import get_model_name
from agents.confirmation import build_confirmation_agent
from agents.conversation import build_conversation_agent
from agents.guest_profiling import build_guest_profiling_agent
from agents.reservation import build_reservation_agent
from agents.room_assignment import build_room_assignment_agent
from agents.support import build_support_agent
from agents.upsell import build_upsell_agent


def build_root_orchestrator() -> LlmAgent:
    return LlmAgent(
        model=get_model_name(),
        name="hotel_root_orchestrator",
        description="Routes hotel requests to specialist agents and coordinates workflow state.",
        instruction=(
            "You are the root orchestrator for Aurora Nexus operations. "
            "Coordinate a premium, stage-aware concierge journey: enquiry, profiling, recommendation, "
            "booking preview, payment, and only then final confirmation. "
            "Route responsibilities as follows: clarification and dialogue to conversation_agent, "
            "profile extraction to guest_profiling_agent, availability/booking to reservation_agent and "
            "room_assignment_agent, payment handling to billing_agent, complaints to support_agent, "
            "and relevant service add-ons to upsell_agent. "
            "If a complaint interrupts any step, prioritize support flow first, then resume booking from the "
            "latest valid stage. "
            "After successful payment, ALWAYS hand off to confirmation_agent for the final guest message."
        ),
        sub_agents=[
            build_conversation_agent(),
            build_guest_profiling_agent(),
            build_reservation_agent(),
            build_room_assignment_agent(),
            build_billing_agent(),
            build_upsell_agent(),
            build_support_agent(),
            build_confirmation_agent(),
        ],
    )
