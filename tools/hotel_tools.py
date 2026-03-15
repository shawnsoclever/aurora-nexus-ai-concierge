from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from tools.sheets_client import SheetValidationError, SheetsClient


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def add_guest(
    client: SheetsClient,
    *,
    name: str,
    age: int,
    guest_type: str,
    stay_purpose: str,
    group_size: int,
    loyalty_status: str,
    visit_count: int,
) -> dict:
    guest_id = f"GST-{uuid4().hex[:8]}"
    payload = {
        "guest_id": guest_id,
        "name": name,
        "age": age,
        "guest_type": guest_type,
        "stay_purpose": stay_purpose,
        "group_size": group_size,
        "loyalty_status": loyalty_status,
        "visit_count": visit_count,
    }
    client.append_row("Guests", payload)
    return payload


def find_available_room(
    client: SheetsClient,
    *,
    room_type: str,
    guest_count: int,
) -> dict | None:
    rooms = client.read_all("Rooms")
    for room in rooms:
        if str(room.get("status", "")).lower() != "available":
            continue
        if room_type and str(room.get("room_type", "")).lower() != room_type.lower():
            continue
        if int(room.get("capacity", 0) or 0) < guest_count:
            continue
        return room
    return None


def create_booking(
    client: SheetsClient,
    *,
    guest_id: str,
    room_id: str,
    checkin_date: str,
    checkout_date: str,
    booking_source: str,
) -> dict:
    # Prevent duplicate booking for same room/checkin_date when status is active.
    existing = client.read_all("Bookings")
    for booking in existing:
        same_room = str(booking.get("room_id")) == room_id
        same_date = str(booking.get("checkin_date")) == checkin_date
        active = str(booking.get("status", "")).lower() in {"pending", "confirmed"}
        if same_room and same_date and active:
            raise SheetValidationError("Double booking prevented for room and check-in date")

    booking_id = f"BKG-{uuid4().hex[:8]}"
    payload = {
        "booking_id": booking_id,
        "guest_id": guest_id,
        "room_id": room_id,
        "checkin_date": checkin_date,
        "checkout_date": checkout_date,
        "booking_created_time": _now_iso(),
        "booking_source": booking_source,
        "status": "pending",
    }
    client.append_row("Bookings", payload)
    # Keep room occupancy in sync with booking assignment.
    client.update_by_primary_key(
        "Rooms",
        room_id,
        {"status": "occupied", "assigned_guest": guest_id},
    )
    return payload


def update_room_status(client: SheetsClient, *, room_id: str, status: str) -> dict:
    client.update_by_primary_key("Rooms", room_id, {"status": status})
    return {"room_id": room_id, "status": status}


def log_payment(
    client: SheetsClient,
    *,
    booking_id: str,
    guest_id: str,
    amount: float,
    payment_status: str,
    transaction_id: str,
) -> dict:
    payment_id = f"PAY-{uuid4().hex[:8]}"
    payload = {
        "payment_id": payment_id,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "amount": amount,
        "payment_status": payment_status,
        "transaction_id": transaction_id,
    }
    client.append_row("Payments", payload)
    return payload


def get_booking(client: SheetsClient, *, booking_id: str) -> dict | None:
    for record in client.read_all("Bookings"):
        if str(record.get("booking_id")) == booking_id:
            return record
    return None


def get_room(client: SheetsClient, *, room_id: str) -> dict | None:
    for record in client.read_all("Rooms"):
        if str(record.get("room_id")) == room_id:
            return record
    return None


def update_booking_status(client: SheetsClient, *, booking_id: str, status: str) -> dict:
    client.update_by_primary_key("Bookings", booking_id, {"status": status})
    return {"booking_id": booking_id, "status": status}


def read_services(client: SheetsClient) -> list[dict]:
    services = client.read_all("Services")
    return [row for row in services if str(row.get("active", "")).lower() in {"true", "1", "yes"}]


def log_complaint(
    client: SheetsClient,
    *,
    guest_id: str,
    booking_id: str,
    issue: str,
    resolution: str = "",
) -> dict:
    complaint_id = f"CMP-{uuid4().hex[:8]}"
    payload = {
        "complaint_id": complaint_id,
        "guest_id": guest_id,
        "booking_id": booking_id,
        "issue": issue,
        "resolution": resolution,
        "status": "open",
    }
    client.append_row("Complaints", payload)
    return payload


def reassign_room_for_complaint(
    client: SheetsClient,
    *,
    guest_id: str,
    booking_id: str,
    issue: str,
) -> dict:
    issue_lc = issue.lower()
    change_room_intent = any(
        keyword in issue_lc
        for keyword in {
            "change room",
            "change my room",
            "room change",
            "noisy",
            "noise",
            "dirty",
            "air conditioning",
            "ac not working",
            "leak",
            "smell",
        }
    )
    if not change_room_intent:
        return {
            "changed": False,
            "reason": "Issue does not require room reassignment.",
        }

    booking = get_booking(client, booking_id=booking_id)
    if not booking:
        raise SheetValidationError(f"Booking not found: {booking_id}")

    if str(booking.get("guest_id", "")) != guest_id:
        raise SheetValidationError("Booking does not belong to the provided guest_id")

    current_room_id = str(booking.get("room_id", ""))
    current_room = get_room(client, room_id=current_room_id)
    if not current_room:
        raise SheetValidationError(f"Current room not found: {current_room_id}")

    room_type = str(current_room.get("room_type", ""))
    current_capacity = int(current_room.get("capacity", 1) or 1)

    candidate = None
    for room in client.read_all("Rooms"):
        if str(room.get("room_id", "")) == current_room_id:
            continue
        if str(room.get("status", "")).lower() != "available":
            continue
        if room_type and str(room.get("room_type", "")).lower() != room_type.lower():
            continue
        if int(room.get("capacity", 0) or 0) < current_capacity:
            continue
        candidate = room
        break

    if not candidate:
        return {
            "changed": False,
            "reason": "No suitable alternative room is currently available.",
            "current_room_id": current_room_id,
        }

    new_room_id = str(candidate.get("room_id", ""))

    # Move assignment from old room to new room and keep booking room_id in sync.
    client.update_by_primary_key(
        "Rooms",
        current_room_id,
        {"status": "available", "assigned_guest": ""},
    )
    client.update_by_primary_key(
        "Rooms",
        new_room_id,
        {"status": "occupied", "assigned_guest": guest_id},
    )
    client.update_by_primary_key("Bookings", booking_id, {"room_id": new_room_id})

    return {
        "changed": True,
        "booking_id": booking_id,
        "guest_id": guest_id,
        "old_room_id": current_room_id,
        "new_room_id": new_room_id,
        "room_type": str(candidate.get("room_type", "")),
    }
