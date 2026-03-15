"""
Agent layer tests – verifies each agent's tool logic, policy allowlist,
and confirmation format. Does NOT call the LLM to avoid quota exhaustion.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.policies import ROLE_TOOL_ALLOWLIST
from guardrails.policy_guard import evaluate_policy
from guardrails.tool_guard import evaluate_tool_call
from tools.hotel_tools import (
    add_guest,
    create_booking,
    find_available_room,
    get_booking,
    get_room,
    log_complaint,
    log_payment,
    reassign_room_for_complaint,
    read_services,
    update_room_status,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _mock_client(sheet_data: dict[str, list[dict]]) -> MagicMock:
    """Returns a SheetsClient mock whose read_all returns the provided lists."""
    client = MagicMock()
    client.read_all.side_effect = lambda name: sheet_data.get(name, [])
    client.append_row.return_value = None
    client.update_by_primary_key.return_value = None
    return client


# ─── Agent 1: conversation_agent ──────────────────────────────────────────────

class TestConversationAgent:
    def test_no_tools_allowed(self) -> None:
        """conversation_agent must not have access to any tools."""
        assert ROLE_TOOL_ALLOWLIST["conversation_agent"] == set()

    def test_any_tool_blocked(self) -> None:
        decision = evaluate_policy(
            correlation_id="cid-conv",
            agent_name="conversation_agent",
            intended_tool="add_guest_tool",
            intent="chat",
        )
        assert decision.decision == "block"
        assert decision.reason_code == "TOOL_NOT_ALLOWED_FOR_AGENT"


# ─── Agent 2: guest_profiling_agent ───────────────────────────────────────────

class TestGuestProfilingAgent:
    def test_only_add_guest_allowed(self) -> None:
        allowed = ROLE_TOOL_ALLOWLIST["guest_profiling_agent"]
        assert allowed == {"add_guest_tool"}

    def test_add_guest_tool_allowed(self) -> None:
        decision = evaluate_policy(
            correlation_id="cid-gp-1",
            agent_name="guest_profiling_agent",
            intended_tool="add_guest_tool",
            intent="profile",
        )
        assert decision.decision == "allow"

    def test_add_guest_writes_all_fields(self) -> None:
        client = _mock_client({})
        result = add_guest(
            client,
            name="Alex Tan",
            age=30,
            guest_type="leisure",
            stay_purpose="vacation",
            group_size=2,
            loyalty_status="none",
            visit_count=1,
        )
        assert result["name"] == "Alex Tan"
        assert result["age"] == 30
        assert result["guest_id"].startswith("GST-")
        client.append_row.assert_called_once_with("Guests", result)

    def test_payment_tool_blocked_for_guest_profiling(self) -> None:
        decision = evaluate_policy(
            correlation_id="cid-gp-2",
            agent_name="guest_profiling_agent",
            intended_tool="log_payment_tool",
            intent="profile",
        )
        assert decision.decision == "block"


# ─── Agent 3: reservation_agent ───────────────────────────────────────────────

class TestReservationAgent:
    def test_tools_allowed(self) -> None:
        allowed = ROLE_TOOL_ALLOWLIST["reservation_agent"]
        assert "find_available_room_tool" in allowed
        assert "create_booking_tool" in allowed

    def test_find_available_room_returns_matching(self) -> None:
        rooms = [
            {"room_id": "101", "room_type": "Standard", "status": "available", "capacity": 2,
             "floor": "1", "zone": "A", "noise_level": "low", "assigned_guest": "",
             "last_cleaned": "", "maintenance_status": "ok"},
            {"room_id": "201", "room_type": "Deluxe", "status": "available", "capacity": 3,
             "floor": "2", "zone": "B", "noise_level": "medium", "assigned_guest": "",
             "last_cleaned": "", "maintenance_status": "ok"},
        ]
        client = _mock_client({"Rooms": rooms})
        result = find_available_room(client, room_type="Deluxe", guest_count=2)
        assert result is not None
        assert result["room_id"] == "201"

    def test_find_available_room_returns_none_if_occupied(self) -> None:
        rooms = [
            {"room_id": "201", "room_type": "Deluxe", "status": "occupied", "capacity": 3,
             "floor": "2", "zone": "B", "noise_level": "medium", "assigned_guest": "GST-1",
             "last_cleaned": "", "maintenance_status": "ok"},
        ]
        client = _mock_client({"Rooms": rooms})
        result = find_available_room(client, room_type="Deluxe", guest_count=2)
        assert result is None

    def test_find_room_capacity_check(self) -> None:
        rooms = [
            {"room_id": "101", "room_type": "Standard", "status": "available", "capacity": 1,
             "floor": "1", "zone": "A", "noise_level": "low", "assigned_guest": "",
             "last_cleaned": "", "maintenance_status": "ok"},
        ]
        client = _mock_client({"Rooms": rooms})
        result = find_available_room(client, room_type="Standard", guest_count=3)
        assert result is None  # capacity=1 < guest_count=3

    def test_create_booking_success(self) -> None:
        client = _mock_client({"Bookings": []})
        result = create_booking(
            client,
            guest_id="GST-abc",
            room_id="201",
            checkin_date="2026-03-20",
            checkout_date="2026-03-22",
            booking_source="direct",
        )
        assert result["booking_id"].startswith("BKG-")
        assert result["status"] == "pending"
        assert result["room_id"] == "201"
        client.update_by_primary_key.assert_called_with(
            "Rooms",
            "201",
            {"status": "occupied", "assigned_guest": "GST-abc"},
        )

    def test_double_booking_prevented(self) -> None:
        existing = [
            {"room_id": "201", "checkin_date": "2026-03-20", "status": "confirmed"}
        ]
        client = _mock_client({"Bookings": existing})
        from tools.sheets_client import SheetValidationError
        with pytest.raises(SheetValidationError, match="Double booking"):
            create_booking(
                client,
                guest_id="GST-xyz",
                room_id="201",
                checkin_date="2026-03-20",
                checkout_date="2026-03-22",
                booking_source="website",
            )

    def test_same_day_booking_blocked_by_tool_guard(self) -> None:
        decision = evaluate_tool_call(
            correlation_id="cid-res-1",
            tool_name="create_booking_tool",
            payload={"checkin_date": "2026-03-20", "checkout_date": "2026-03-20"},
        )
        assert decision.decision == "block"
        assert decision.reason_code == "INVALID_BOOKING_DATES"

    def test_valid_booking_dates_allowed(self) -> None:
        decision = evaluate_tool_call(
            correlation_id="cid-res-2",
            tool_name="create_booking_tool",
            payload={"checkin_date": "2026-03-20", "checkout_date": "2026-03-22"},
        )
        assert decision.decision == "allow"


# ─── Agent 4: room_assignment_agent ───────────────────────────────────────────

class TestRoomAssignmentAgent:
    def test_tools_allowed(self) -> None:
        allowed = ROLE_TOOL_ALLOWLIST["room_assignment_agent"]
        assert "find_available_room_tool" in allowed
        assert "update_room_status_tool" in allowed

    def test_update_room_status(self) -> None:
        client = _mock_client({})
        result = update_room_status(client, room_id="201", status="occupied")
        assert result == {"room_id": "201", "status": "occupied"}
        client.update_by_primary_key.assert_called_once_with(
            "Rooms", "201", {"status": "occupied"}
        )

    def test_billing_tool_blocked(self) -> None:
        decision = evaluate_policy(
            correlation_id="cid-ra",
            agent_name="room_assignment_agent",
            intended_tool="log_payment_tool",
            intent="room",
        )
        assert decision.decision == "block"


# ─── Agent 5: billing_agent ───────────────────────────────────────────────────

class TestBillingAgent:
    def test_only_log_payment_allowed(self) -> None:
        assert ROLE_TOOL_ALLOWLIST["billing_agent"] == {
            "log_payment_tool",
            "update_booking_status_tool",
        }

    def test_log_payment_writes_correctly(self) -> None:
        client = _mock_client({})
        result = log_payment(
            client,
            booking_id="BKG-abc",
            guest_id="GST-abc",
            amount=350.0,
            payment_status="success",
            transaction_id="TXN-001",
        )
        assert result["payment_id"].startswith("PAY-")
        assert result["amount"] == 350.0
        assert result["payment_status"] == "success"
        assert result["transaction_id"] == "TXN-001"

    def test_zero_payment_blocked_by_tool_guard(self) -> None:
        decision = evaluate_tool_call(
            correlation_id="cid-bill-1",
            tool_name="log_payment_tool",
            payload={"amount": 0},
        )
        assert decision.decision == "block"
        assert decision.reason_code == "INVALID_PAYMENT_AMOUNT"

    def test_negative_payment_blocked(self) -> None:
        decision = evaluate_tool_call(
            correlation_id="cid-bill-2",
            tool_name="log_payment_tool",
            payload={"amount": -100},
        )
        assert decision.decision == "block"

    def test_positive_payment_allowed(self) -> None:
        decision = evaluate_tool_call(
            correlation_id="cid-bill-3",
            tool_name="log_payment_tool",
            payload={"amount": 1.0},
        )
        assert decision.decision == "allow"


# ─── Agent 6: upsell_agent ────────────────────────────────────────────────────

class TestUpsellAgent:
    def test_only_read_services_allowed(self) -> None:
        assert ROLE_TOOL_ALLOWLIST["upsell_agent"] == {"read_services_tool"}

    def test_read_services_filters_active(self) -> None:
        services = [
            {"service_id": "SVC-1", "service_name": "Breakfast", "description": "Buffet",
             "price": 25, "active": "true"},
            {"service_id": "SVC-2", "service_name": "Spa", "description": "Relaxation",
             "price": 120, "active": "false"},
            {"service_id": "SVC-3", "service_name": "Transfer", "description": "Airport",
             "price": 80, "active": "1"},
        ]
        client = _mock_client({"Services": services})
        result = read_services(client)
        names = [s["service_name"] for s in result]
        assert "Breakfast" in names
        assert "Transfer" in names
        assert "Spa" not in names  # inactive

    def test_booking_tool_blocked_for_upsell(self) -> None:
        decision = evaluate_policy(
            correlation_id="cid-ups",
            agent_name="upsell_agent",
            intended_tool="create_booking_tool",
            intent="upsell",
        )
        assert decision.decision == "block"


# ─── Agent 7: support_agent ───────────────────────────────────────────────────

class TestSupportAgent:
    def test_support_tools_allowed(self) -> None:
        assert ROLE_TOOL_ALLOWLIST["support_agent"] == {
            "log_complaint_tool",
            "reassign_room_for_complaint_tool",
        }

    def test_log_complaint_writes_correctly(self) -> None:
        client = _mock_client({})
        result = log_complaint(
            client,
            guest_id="GST-abc",
            booking_id="BKG-abc",
            issue="Room AC is not working",
            resolution="",
        )
        assert result["complaint_id"].startswith("CMP-")
        assert result["status"] == "open"
        assert result["issue"] == "Room AC is not working"
        assert result["resolution"] == ""

    def test_complaint_with_resolution(self) -> None:
        client = _mock_client({})
        result = log_complaint(
            client,
            guest_id="GST-abc",
            booking_id="BKG-abc",
            issue="Noisy neighbours",
            resolution="Moved guest to quieter floor",
        )
        assert result["resolution"] == "Moved guest to quieter floor"

    def test_payment_tool_blocked_for_support(self) -> None:
        decision = evaluate_policy(
            correlation_id="cid-sup",
            agent_name="support_agent",
            intended_tool="log_payment_tool",
            intent="complaint",
        )
        assert decision.decision == "block"

    def test_reassign_room_for_complaint_changes_assignment(self) -> None:
        client = _mock_client(
            {
                "Bookings": [
                    {
                        "booking_id": "BKG-abc",
                        "guest_id": "GST-abc",
                        "room_id": "101",
                        "checkin_date": "2026-03-20",
                        "checkout_date": "2026-03-22",
                        "booking_created_time": "2026-03-15T12:00:00Z",
                        "booking_source": "direct",
                        "status": "pending",
                    }
                ],
                "Rooms": [
                    {
                        "room_id": "101",
                        "floor": "1",
                        "room_type": "Deluxe",
                        "zone": "Leisure",
                        "capacity": 2,
                        "noise_level": "high",
                        "status": "occupied",
                        "assigned_guest": "GST-abc",
                        "last_cleaned": "",
                        "maintenance_status": "ok",
                    },
                    {
                        "room_id": "201",
                        "floor": "2",
                        "room_type": "Deluxe",
                        "zone": "Leisure",
                        "capacity": 3,
                        "noise_level": "medium",
                        "status": "available",
                        "assigned_guest": "",
                        "last_cleaned": "",
                        "maintenance_status": "ok",
                    },
                ],
            }
        )

        result = reassign_room_for_complaint(
            client,
            guest_id="GST-abc",
            booking_id="BKG-abc",
            issue="The room is noisy, please change room",
        )

        assert result["changed"] is True
        assert result["old_room_id"] == "101"
        assert result["new_room_id"] == "201"

    def test_reassign_room_for_complaint_no_change_when_unrelated(self) -> None:
        client = _mock_client({"Bookings": [], "Rooms": []})
        result = reassign_room_for_complaint(
            client,
            guest_id="GST-abc",
            booking_id="BKG-abc",
            issue="Need extra towels",
        )
        assert result["changed"] is False


# ─── Agent 8: confirmation_agent ──────────────────────────────────────────────

class TestConfirmationAgent:
    def test_tools_allowed(self) -> None:
        allowed = ROLE_TOOL_ALLOWLIST["confirmation_agent"]
        assert allowed == {"get_booking_tool", "get_room_tool"}

    def test_get_booking_returns_record(self) -> None:
        bookings = [
            {"booking_id": "BKG-abc123", "guest_id": "GST-1", "room_id": "201",
             "checkin_date": "2026-03-20", "checkout_date": "2026-03-22",
             "booking_created_time": "2026-03-15T12:00:00Z", "booking_source": "direct",
             "status": "pending"},
        ]
        client = _mock_client({"Bookings": bookings})
        result = get_booking(client, booking_id="BKG-abc123")
        assert result is not None
        assert result["booking_id"] == "BKG-abc123"
        assert result["room_id"] == "201"

    def test_get_booking_returns_none_for_unknown(self) -> None:
        client = _mock_client({"Bookings": []})
        result = get_booking(client, booking_id="BKG-nonexistent")
        assert result is None

    def test_get_room_returns_record(self) -> None:
        rooms = [
            {"room_id": "201", "floor": "2", "room_type": "Deluxe", "zone": "Leisure",
             "capacity": 3, "noise_level": "medium", "status": "occupied",
             "assigned_guest": "GST-1", "last_cleaned": "", "maintenance_status": "ok"},
        ]
        client = _mock_client({"Rooms": rooms})
        result = get_room(client, room_id="201")
        assert result is not None
        assert result["room_type"] == "Deluxe"
        assert result["floor"] == "2"
        assert result["zone"] == "Leisure"

    def test_get_room_returns_none_for_unknown(self) -> None:
        client = _mock_client({"Rooms": []})
        result = get_room(client, room_id="999")
        assert result is None

    def test_confirmation_agent_cannot_write(self) -> None:
        """Confirm confirmation_agent is not allowed to use write tools."""
        for write_tool in ["add_guest_tool", "create_booking_tool",
                           "update_room_status_tool", "log_payment_tool",
                           "log_complaint_tool"]:
            decision = evaluate_policy(
                correlation_id="cid-conf",
                agent_name="confirmation_agent",
                intended_tool=write_tool,
                intent="confirmation",
            )
            assert decision.decision == "block", (
                f"confirmation_agent must not access write tool: {write_tool}"
            )

    def test_confirmation_read_tools_allowed(self) -> None:
        for read_tool in ["get_booking_tool", "get_room_tool"]:
            decision = evaluate_policy(
                correlation_id="cid-conf-read",
                agent_name="confirmation_agent",
                intended_tool=read_tool,
                intent="confirmation",
            )
            assert decision.decision == "allow", (
                f"confirmation_agent must be able to call: {read_tool}"
            )

    def test_full_confirmation_data_pipeline(self) -> None:
        """Simulates the full data path: booking → room_id → room details."""
        bookings = [
            {"booking_id": "BKG-test99", "guest_id": "GST-1", "room_id": "201",
             "checkin_date": "2026-03-20", "checkout_date": "2026-03-22",
             "booking_created_time": "2026-03-15T12:00:00Z", "booking_source": "direct",
             "status": "pending"},
        ]
        rooms = [
            {"room_id": "201", "floor": "2", "room_type": "Deluxe", "zone": "Leisure",
             "capacity": 3, "noise_level": "medium", "status": "occupied",
             "assigned_guest": "GST-1", "last_cleaned": "", "maintenance_status": "ok"},
        ]
        client = _mock_client({"Bookings": bookings, "Rooms": rooms})

        booking = get_booking(client, booking_id="BKG-test99")
        assert booking is not None

        room = get_room(client, room_id=booking["room_id"])
        assert room is not None

        # Verify all expected confirmation fields are present
        assert booking["booking_id"] == "BKG-test99"
        assert booking["checkin_date"] == "2026-03-20"
        assert booking["checkout_date"] == "2026-03-22"
        assert room["room_type"] == "Deluxe"
        assert room["floor"] == "2"
        assert room["zone"] == "Leisure"
        assert int(room["capacity"]) >= 1
        assert room["noise_level"] == "medium"
