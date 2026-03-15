from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import api.routes as routes
from main import app


class FakeSheetsClient:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            "Rooms": [
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
                }
            ],
            "Bookings": [],
            "Payments": [],
            "Services": [],
            "Guests": [],
            "Complaints": [],
        }

    def read_all(self, sheet_name: str) -> list[dict[str, Any]]:
        return self._tables[sheet_name]

    def append_row(self, sheet_name: str, payload: dict[str, Any]) -> None:
        self._tables[sheet_name].append(payload)

    def update_by_primary_key(self, sheet_name: str, key_value: str, payload: dict[str, Any]) -> None:
        key_name = {
            "Rooms": "room_id",
            "Bookings": "booking_id",
            "Payments": "payment_id",
            "Guests": "guest_id",
            "Complaints": "complaint_id",
            "Services": "service_id",
        }[sheet_name]
        for row in self._tables[sheet_name]:
            if str(row.get(key_name, "")) == str(key_value):
                row.update(payload)
                return
        raise ValueError(f"Row not found in {sheet_name} for key {key_value}")


def _chat_payload(session_id: str, message: str) -> dict[str, str]:
    return {
        "session_id": session_id,
        "user_id": "GST-test",
        "message": message,
    }


def _booking_preview_payload(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "guest_id": "GST-test",
        "guest_name": "Alex Tan",
        "stay_purpose": "leisure",
        "checkin_date": "2026-03-20",
        "checkout_date": "2026-03-22",
        "room_type": "Deluxe",
        "room_id": "201",
        "guest_count": 2,
    }


def _booking_payload(session_id: str) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "guest_id": "GST-test",
        "checkin_date": "2026-03-20",
        "checkout_date": "2026-03-22",
        "room_type": "Deluxe",
        "room_id": "201",
        "guest_count": 2,
        "booking_source": "direct",
    }


def test_booking_without_preview_blocked(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    client = TestClient(app)
    response = client.post("/booking", json=_booking_payload("sess-no-preview"))

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["reason_code"] == "PREVIEW_REQUIRED"


def test_payment_without_booking_stage_blocked(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    client = TestClient(app)
    response = client.post(
        "/payment",
        json={
            "session_id": "sess-no-payment-stage",
            "user_id": "GST-test",
            "booking_id": "BKG-none",
            "guest_id": "GST-test",
            "amount": 100.0,
            "payment_status": "success",
            "transaction_id": "TXN-001",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["reason_code"] == "PAYMENT_STAGE_REQUIRED"


def test_confirmation_before_payment_blocked(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "stub"

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-chat-block", "Please confirm booking now."),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["reason_code"] == "CONFIRMATION_REQUIRES_PAYMENT"


def test_confirmation_intent_blocked_when_not_confirmation_stage(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "stub"

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    state = routes.session_manager.get_workflow_state("sess-stale-paid")
    state.stage = "preview"
    state.payment_confirmed = True

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-stale-paid", "Please confirm booking now."),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["reason_code"] == "CONFIRMATION_REQUIRES_PAYMENT"


def test_opening_chat_requests_guest_name_first(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "stub"

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-open-ask-name", "Hello, I want to book a room."),
    )

    assert response.status_code == 200
    body = response.json()
    assert "May I have your name" in body["response"]


def test_after_name_chat_requests_dates_and_guest_count(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "stub"

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-name-next-step", "My name is Daniel Tan."),
    )

    assert response.status_code == 200
    body = response.json()
    assert "Wonderful to meet you" in body["response"]
    assert "check-in" in body["response"]


def test_chat_with_profile_details_returns_room_recommendation_not_confirmation(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "Your booking is confirmed."

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    client = TestClient(app)
    session_id = "sess-recommendation-guard"

    first = client.post(
        "/chat",
        json=_chat_payload(session_id, "My name is Shawn."),
    )
    assert first.status_code == 200

    second = client.post(
        "/chat",
        json=_chat_payload(session_id, "2 guests, vacation, good view"),
    )

    assert second.status_code == 200
    body = second.json()
    assert "check-in and check-out dates" in body["response"]
    assert "booking is confirmed" not in body["response"].lower()
    assert body["metadata"]["stage"] == "recommendation"
    assert body["metadata"]["payment_confirmed"] is False
    assert "recommended_rooms" not in body["metadata"]


def test_chat_blocks_premature_confirmation_text_before_confirmation_stage(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "Great news. Your booking is confirmed and finalized."

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    state = routes.session_manager.get_workflow_state("sess-no-early-confirm")
    state.stage = "preview"
    state.guest_profile["guest_name"] = "Alex"

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-no-early-confirm", "Can you give me an update?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert "not finalized" in body["response"].lower()
    assert "booking is confirmed" not in body["response"].lower()


def test_rooms_requires_guest_name_before_recommendation(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    client = TestClient(app)
    response = client.get(
        "/rooms",
        params={
            "session_id": "sess-no-name",
            "user_id": "GST-test",
            "checkin_date": "2026-03-20",
            "checkout_date": "2026-03-22",
            "guest_count": 2,
            "room_type": "Deluxe",
        },
    )

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["reason_code"] == "PROFILE_STAGE_REQUIRED"


def test_booking_preview_requires_guest_name(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    client = TestClient(app)
    session_id = "sess-profile-required"

    payload = _booking_preview_payload(session_id)
    payload["guest_name"] = None
    response = client.post("/booking/preview", json=payload)

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"]["reason_code"] == "PROFILE_STAGE_REQUIRED"


def test_happy_path_preview_booking_payment_and_chat_confirmation(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        return "Booking confirmed summary"

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    client = TestClient(app)
    session_id = "sess-happy-path"

    profile_chat = client.post(
        "/chat",
        json=_chat_payload(session_id, "My name is Alex Tan. I want to book a deluxe room for 2 guests."),
    )
    assert profile_chat.status_code == 200

    rooms_response = client.get(
        "/rooms",
        params={
            "session_id": session_id,
            "user_id": "GST-test",
            "checkin_date": "2026-03-20",
            "checkout_date": "2026-03-22",
            "guest_count": 2,
            "room_type": "Deluxe",
        },
    )
    assert rooms_response.status_code == 200

    preview_response = client.post("/booking/preview", json=_booking_preview_payload(session_id))
    assert preview_response.status_code == 200

    booking_response = client.post("/booking", json=_booking_payload(session_id))
    assert booking_response.status_code == 200
    booking_id = booking_response.json()["booking_id"]

    payment_preview_response = client.post(
        "/payment/preview",
        json={"session_id": session_id, "booking_id": booking_id},
    )
    assert payment_preview_response.status_code == 200
    amount = payment_preview_response.json()["amount"]

    payment_response = client.post(
        "/payment",
        json={
            "session_id": session_id,
            "user_id": "GST-test",
            "booking_id": booking_id,
            "guest_id": "GST-test",
            "amount": amount,
            "payment_status": "success",
            "transaction_id": "TXN-OK-1",
        },
    )
    assert payment_response.status_code == 200

    chat_response = client.post(
        "/chat",
        json=_chat_payload(session_id, f"Please confirm booking {booking_id} now."),
    )
    assert chat_response.status_code == 200
    chat_body = chat_response.json()
    assert chat_body["metadata"]["stage"] == "confirmation"
    assert chat_body["metadata"]["payment_confirmed"] is True


def test_chat_confirmation_falls_back_when_model_quota_exhausted(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    state = routes.session_manager.get_workflow_state("sess-confirm-fallback")
    state.stage = "confirmation"
    state.payment_confirmed = True
    state.final_booking_id = "BKG-fallback"

    fake_client._tables["Bookings"].append(
        {
            "booking_id": "BKG-fallback",
            "guest_id": "GST-test",
            "room_id": "201",
            "checkin_date": "2026-03-20",
            "checkout_date": "2026-03-22",
            "booking_created_time": "2026-03-15T12:00:00Z",
            "booking_source": "direct",
            "status": "confirmed",
        }
    )

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-confirm-fallback", "confirm booking"),
    )

    assert response.status_code == 200
    body = response.json()
    assert "Booking Confirmed" in body["response"]
    assert "BKG-fallback" in body["response"]
    assert body["metadata"]["stage"] == "confirmation"
    assert body["metadata"]["payment_confirmed"] is True


def test_confirmation_stage_complaint_message_not_replaced_by_confirmation(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    async def _fake_run_agent(*, user_id: str, session_id: str, message: str) -> str:
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(routes, "run_agent", _fake_run_agent)

    state = routes.session_manager.get_workflow_state("sess-complaint-followup")
    state.stage = "confirmation"
    state.payment_confirmed = True
    state.final_booking_id = "BKG-followup"

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-complaint-followup", "I would like to make a complaint about a dirty room."),
    )

    assert response.status_code == 200
    body = response.json()
    assert "file a complaint" in body["response"].lower()
    assert "booking confirmed" not in body["response"].lower()


def test_confirmation_stage_services_request_returns_service_options(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    fake_client._tables["Services"] = [
        {
            "service_id": "SVC-1",
            "service_name": "Breakfast",
            "description": "Buffet breakfast",
            "price": 12,
            "active": "true",
        }
    ]
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    state = routes.session_manager.get_workflow_state("sess-services-followup")
    state.stage = "confirmation"
    state.payment_confirmed = True
    state.final_booking_id = "BKG-services"

    client = TestClient(app)
    response = client.post(
        "/chat",
        json=_chat_payload("sess-services-followup", "What services do you have?"),
    )

    assert response.status_code == 200
    body = response.json()
    assert "add-on services" in body["response"].lower()
    assert "breakfast" in body["response"].lower()


def test_confirmation_stage_new_reservation_resets_flow_with_existing_name(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    client = TestClient(app)
    session_id = "sess-new-booking-after-confirm"

    state = routes.session_manager.get_workflow_state(session_id)
    state.stage = "confirmation"
    state.payment_confirmed = True
    state.final_booking_id = "BKG-prev"
    state.guest_profile["guest_name"] = "Alexis"

    response = client.post(
        "/chat",
        json=_chat_payload(session_id, "I would like to make a new reservation"),
    )

    assert response.status_code == 200
    body = response.json()
    assert "new reservation" in body["response"].lower()
    assert "check-in and check-out" in body["response"].lower()
    assert body["metadata"]["stage"] == "profiling"


def test_confirmation_stage_new_reservation_asks_name_when_missing(monkeypatch) -> None:
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(routes, "_get_sheets_client", lambda: fake_client)

    client = TestClient(app)
    session_id = "sess-new-booking-no-name"

    state = routes.session_manager.get_workflow_state(session_id)
    state.stage = "confirmation"
    state.payment_confirmed = True
    state.final_booking_id = "BKG-prev-2"
    state.guest_profile.pop("guest_name", None)

    response = client.post(
        "/chat",
        json=_chat_payload(session_id, "book a new room"),
    )

    assert response.status_code == 200
    body = response.json()
    assert "may i have your name" in body["response"].lower()
