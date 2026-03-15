from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyRule:
    name: str
    description: str


ROLE_TOOL_ALLOWLIST: dict[str, set[str]] = {
    "conversation_agent": set(),
    "guest_profiling_agent": {"add_guest_tool"},
    "reservation_agent": {"find_available_room_tool", "create_booking_tool"},
    "room_assignment_agent": {"find_available_room_tool", "update_room_status_tool"},
    "billing_agent": {"log_payment_tool", "update_booking_status_tool"},
    "upsell_agent": {"read_services_tool"},
    "support_agent": {"log_complaint_tool", "reassign_room_for_complaint_tool"},
    "confirmation_agent": {"get_booking_tool", "get_room_tool"},
}


POLICY_RULES: list[PolicyRule] = [
    PolicyRule(
        name="NO_PK_MUTATION",
        description="Primary keys cannot be modified through update operations.",
    ),
    PolicyRule(
        name="PAYMENT_AMOUNT_POSITIVE",
        description="Payment amount must be positive and align with booking context.",
    ),
    PolicyRule(
        name="BOOKING_REQUIRES_VALID_DATES",
        description="Booking operations must include valid date and stay constraints.",
    ),
]
