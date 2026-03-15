from uuid import uuid4
from functools import lru_cache
import os

from fastmcp import FastMCP

from core.guardrail_manager import GuardrailManager
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
    update_booking_status,
    update_room_status,
)
from tools.sheets_client import SheetsClient

mcp = FastMCP("Hotel MCP Server")
guardrails = GuardrailManager()


def _enforce_tool_guard(tool_name: str, payload: dict) -> None:
    decision = guardrails.check_tool(
        correlation_id=uuid4().hex,
        tool_name=tool_name,
        payload=payload,
    )
    if decision.decision == "block":
        raise ValueError(f"Guardrail blocked tool call: {decision.reason_code}")


@lru_cache(maxsize=1)
def _get_client() -> SheetsClient:
    return SheetsClient()


@mcp.tool()
def add_guest_tool(
    name: str,
    age: int,
    guest_type: str,
    stay_purpose: str,
    group_size: int,
    loyalty_status: str,
    visit_count: int,
) -> dict:
    _enforce_tool_guard(
        "add_guest_tool",
        {
            "name": name,
            "age": age,
            "guest_type": guest_type,
            "stay_purpose": stay_purpose,
            "group_size": group_size,
            "loyalty_status": loyalty_status,
            "visit_count": visit_count,
        },
    )
    return add_guest(
        _get_client(),
        name=name,
        age=age,
        guest_type=guest_type,
        stay_purpose=stay_purpose,
        group_size=group_size,
        loyalty_status=loyalty_status,
        visit_count=visit_count,
    )


@mcp.tool()
def find_available_room_tool(room_type: str, guest_count: int) -> dict | None:
    _enforce_tool_guard(
        "find_available_room_tool",
        {"room_type": room_type, "guest_count": guest_count},
    )
    return find_available_room(_get_client(), room_type=room_type, guest_count=guest_count)


@mcp.tool()
def create_booking_tool(
    guest_id: str,
    room_id: str,
    checkin_date: str,
    checkout_date: str,
    booking_source: str,
) -> dict:
    _enforce_tool_guard(
        "create_booking_tool",
        {
            "guest_id": guest_id,
            "room_id": room_id,
            "checkin_date": checkin_date,
            "checkout_date": checkout_date,
            "booking_source": booking_source,
        },
    )
    return create_booking(
        _get_client(),
        guest_id=guest_id,
        room_id=room_id,
        checkin_date=checkin_date,
        checkout_date=checkout_date,
        booking_source=booking_source,
    )


@mcp.tool()
def update_room_status_tool(room_id: str, status: str) -> dict:
    _enforce_tool_guard("update_room_status_tool", {"room_id": room_id, "status": status})
    return update_room_status(_get_client(), room_id=room_id, status=status)


@mcp.tool()
def log_payment_tool(booking_id: str, guest_id: str, amount: float, payment_status: str, transaction_id: str) -> dict:
    _enforce_tool_guard(
        "log_payment_tool",
        {
            "booking_id": booking_id,
            "guest_id": guest_id,
            "amount": amount,
            "payment_status": payment_status,
            "transaction_id": transaction_id,
        },
    )
    return log_payment(
        _get_client(),
        booking_id=booking_id,
        guest_id=guest_id,
        amount=amount,
        payment_status=payment_status,
        transaction_id=transaction_id,
    )


@mcp.tool()
def update_booking_status_tool(booking_id: str, status: str) -> dict:
    _enforce_tool_guard(
        "update_booking_status_tool",
        {
            "booking_id": booking_id,
            "status": status,
        },
    )
    return update_booking_status(_get_client(), booking_id=booking_id, status=status)


@mcp.tool()
def get_booking_tool(booking_id: str) -> dict | None:
    _enforce_tool_guard("get_booking_tool", {"booking_id": booking_id})
    return get_booking(_get_client(), booking_id=booking_id)


@mcp.tool()
def get_room_tool(room_id: str) -> dict | None:
    _enforce_tool_guard("get_room_tool", {"room_id": room_id})
    return get_room(_get_client(), room_id=room_id)


@mcp.tool()
def read_services_tool() -> list[dict]:
    _enforce_tool_guard("read_services_tool", {})
    return read_services(_get_client())


@mcp.tool()
def log_complaint_tool(guest_id: str, booking_id: str, issue: str, resolution: str = "") -> dict:
    _enforce_tool_guard(
        "log_complaint_tool",
        {
            "guest_id": guest_id,
            "booking_id": booking_id,
            "issue": issue,
            "resolution": resolution,
        },
    )
    return log_complaint(
        _get_client(),
        guest_id=guest_id,
        booking_id=booking_id,
        issue=issue,
        resolution=resolution,
    )


@mcp.tool()
def reassign_room_for_complaint_tool(guest_id: str, booking_id: str, issue: str) -> dict:
    _enforce_tool_guard(
        "reassign_room_for_complaint_tool",
        {
            "guest_id": guest_id,
            "booking_id": booking_id,
            "issue": issue,
        },
    )
    return reassign_room_for_complaint(
        _get_client(),
        guest_id=guest_id,
        booking_id=booking_id,
        issue=issue,
    )


if __name__ == "__main__":
    mcp_port = int(os.getenv("PORT", "8080"))
    mcp.run(transport="http", host="0.0.0.0", port=mcp_port, path="/mcp")
