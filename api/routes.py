from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.errors import ErrorDetail, ErrorResponse
from api.schemas import (
    BookingRequest,
    BookingPreviewCancelRequest,
    BookingPreviewRequest,
    BookingPreviewResponse,
    BookingResponse,
    ChatRequest,
    ChatResponse,
    ComplaintRequest,
    ComplaintResponse,
    PaymentRequest,
    PaymentPreviewRequest,
    PaymentPreviewResponse,
    PaymentResponse,
    PaymentCancelRequest,
    RoomOption,
    RoomQuery,
    RoomsResponse,
    StageTransitionResponse,
)
from core.guardrail_manager import GuardrailManager
from core.config import get_settings
from core.session import session_manager
from observability.audit import audit_event
from orchestrator.runner import run_agent
from tools.hotel_tools import create_booking, log_complaint, log_payment
from tools.hotel_tools import read_services
from tools.hotel_tools import reassign_room_for_complaint
from tools.hotel_tools import update_booking_status
from tools.sheets_client import SheetValidationError, SheetsClient

router = APIRouter()
guardrails = GuardrailManager()

ROOM_RATE_CARD = {
    "standard": 180.0,
    "deluxe": 250.0,
    "suite": 420.0,
    "executive suite": 420.0,
}

PREMATURE_CONFIRMATION_PATTERNS = (
    "booking confirmed",
    "your booking is confirmed",
    "reservation confirmed",
    "booking has been confirmed",
    "confirmed reservation",
)


@lru_cache(maxsize=1)
def _get_sheets_client() -> SheetsClient:
    return SheetsClient()


def _room_rate(room_type: str) -> float:
    return ROOM_RATE_CARD.get(room_type.strip().lower(), 250.0)


def _build_alternative_date_ranges(checkin_date: str, checkout_date: str) -> list[str]:
    checkin = date.fromisoformat(checkin_date)
    checkout = date.fromisoformat(checkout_date)
    duration_days = max((checkout - checkin).days, 1)

    # Offer nearby windows rather than repeating a hard "fully booked" response.
    alternatives: list[str] = []
    for offset in (2, 5, 8):
        alt_checkin = checkin + timedelta(days=offset)
        alt_checkout = alt_checkin + timedelta(days=duration_days)
        alternatives.append(f"{alt_checkin.isoformat()} to {alt_checkout.isoformat()}")
    return alternatives


def _parse_human_date(value: str) -> date | None:
    text = value.strip()
    patterns = ["%d %B %Y", "%d %b %Y"]
    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _extract_guest_profile(state, message: str) -> None:
    lowered = message.lower()
    profile = state.guest_profile

    name_match = re.search(r"(?:my name is|i am|i'm)\s+([a-zA-Z][a-zA-Z\s'-]{1,40})", message, flags=re.IGNORECASE)
    if name_match:
        profile["guest_name"] = name_match.group(1).strip()

    if "business" in lowered:
        profile["stay_purpose"] = "business"
    elif "leisure" in lowered or "vacation" in lowered or "holiday" in lowered:
        profile["stay_purpose"] = "leisure"

    if "deluxe" in lowered:
        profile["room_preference"] = "Deluxe"
    elif "standard" in lowered:
        profile["room_preference"] = "Standard"
    elif "executive suite" in lowered:
        profile["room_preference"] = "Executive Suite"
    elif "suite" in lowered:
        profile["room_preference"] = "Suite"

    guest_count_match = re.search(r"(\d+)\s*(?:guest|guests|pax|people|person)", lowered)
    if guest_count_match:
        profile["guest_count"] = int(guest_count_match.group(1))
    elif any(token in lowered for token in {"travelling alone", "traveling alone", "alone", "solo", "by myself", "just me"}):
        profile["guest_count"] = 1

    date_range_match = re.search(
        r"(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)\s*(?:to|until|till|til|-|–)\s*(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)",
        message,
        flags=re.IGNORECASE,
    )
    if date_range_match:
        current_year = str(date.today().year)
        start_raw = date_range_match.group(1).strip()
        end_raw = date_range_match.group(2).strip()
        if not re.search(r"\b\d{4}\b", start_raw):
            start_raw = f"{start_raw} {current_year}"
        if not re.search(r"\b\d{4}\b", end_raw):
            end_raw = f"{end_raw} {current_year}"
        checkin = _parse_human_date(start_raw)
        checkout = _parse_human_date(end_raw)
        if checkin and checkout and checkout > checkin:
            profile["checkin_date"] = checkin.isoformat()
            profile["checkout_date"] = checkout.isoformat()

    compact_range_match = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s*(\d{4})?", message, flags=re.IGNORECASE)
    if compact_range_match:
        start_day = int(compact_range_match.group(1))
        end_day = int(compact_range_match.group(2))
        month_text = compact_range_match.group(3)
        year_text = compact_range_match.group(4) or str(date.today().year)
        if end_day > start_day:
            checkin = _parse_human_date(f"{start_day} {month_text} {year_text}")
            checkout = _parse_human_date(f"{end_day} {month_text} {year_text}")
            if checkin and checkout and checkout > checkin:
                profile["checkin_date"] = checkin.isoformat()
                profile["checkout_date"] = checkout.isoformat()


def _profile_missing_for_recommendation(state) -> list[str]:
    missing: list[str] = []
    profile = state.guest_profile

    if not profile.get("guest_name"):
        missing.append("guest_name")
    if not profile.get("stay_purpose"):
        missing.append("stay_purpose")
    if not profile.get("guest_count"):
        missing.append("guest_count")
    if not profile.get("checkin_date") or not profile.get("checkout_date"):
        missing.append("stay_dates")

    return missing


def _recommend_rooms_for_chat(state) -> list[RoomOption]:
    profile = state.guest_profile
    preferred_room_type = str(profile.get("room_preference", "")).strip()
    guest_count = int(profile.get("guest_count", 1) or 1)

    available_rooms: list[dict] = []
    for room in _get_sheets_client().read_all("Rooms"):
        if str(room.get("status", "")).lower() != "available":
            continue
        if preferred_room_type and str(room.get("room_type", "")).lower() != preferred_room_type.lower():
            continue
        if int(room.get("capacity", 0) or 0) < guest_count:
            continue
        available_rooms.append(room)

    available_rooms = sorted(
        available_rooms,
        key=lambda item: _room_rate(str(item.get("room_type", ""))),
    )[:3]

    state.recommended_room_ids = [str(room.get("room_id", "")) for room in available_rooms]

    return [
        RoomOption(
            room_id=str(room.get("room_id", "")),
            floor=str(room.get("floor", "")),
            room_type=str(room.get("room_type", "")),
            zone=str(room.get("zone", "")),
            capacity=int(room.get("capacity", 0) or 0),
            price_per_night=_room_rate(str(room.get("room_type", ""))),
            noise_level=str(room.get("noise_level", "")),
            status=str(room.get("status", "")),
            maintenance_status=str(room.get("maintenance_status", "")),
        )
        for room in available_rooms
    ]


def _build_room_recommendation_message(state, rooms: list[RoomOption]) -> str:
    guest_name = str(state.guest_profile.get("guest_name", "there")).strip() or "there"
    stay_purpose = str(state.guest_profile.get("stay_purpose", "your stay")).strip() or "your stay"

    if not rooms:
        return (
            f"Thank you, {guest_name}. I understand this stay is for {stay_purpose}. "
            "I checked our current room inventory and nothing matching your request is available right now. "
            "Please share alternative dates or a different room preference, and I will recommend options immediately."
        )

    lines = [
        f"Thank you, {guest_name}. I understand this stay is for {stay_purpose}.",
        "Let me check the available rooms that match your preference.",
        "Here are a few options I found for you:",
    ]
    for index, room in enumerate(rooms, start=1):
        lines.append(
            (
                f"{index}. {room.room_type} - Room {room.room_id} | "
                f"Floor {room.floor} | Zone {room.zone} | "
                f"Capacity {room.capacity} guests | "
                f"Price MYR {room.price_per_night:.2f}/night"
            )
        )

    lines.append("Which room would you like to reserve?")
    return "\n".join(lines)


def _is_premature_confirmation_text(response_text: str) -> bool:
    lowered = response_text.lower()
    return any(pattern in lowered for pattern in PREMATURE_CONFIRMATION_PATTERNS)


def _chat_metadata(state, **extra: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "stage": state.stage,
        "payment_confirmed": state.payment_confirmed,
    }
    if state.final_booking_id:
        metadata["final_booking_id"] = state.final_booking_id
    metadata.update(extra)
    return metadata


def _build_final_confirmation_from_state(state) -> str | None:
    booking_id = str(state.final_booking_id or "").strip()
    if not booking_id:
        return None

    booking = None
    for record in _get_sheets_client().read_all("Bookings"):
        if str(record.get("booking_id", "")) == booking_id:
            booking = record
            break

    if not booking:
        return None

    room_id = str(booking.get("room_id", "") or "")
    room = None
    if room_id:
        for record in _get_sheets_client().read_all("Rooms"):
            if str(record.get("room_id", "")) == room_id:
                room = record
                break

    def _v(value: object, fallback: str = "N/A") -> str:
        text = str(value).strip() if value is not None else ""
        return text or fallback

    return "\n".join(
        [
            "---",
            "Booking Confirmed",
            "",
            f"Booking ID: {booking_id}",
            "",
            "Room Details",
            f"Room ID:     {_v(room_id)}",
            f"Room Type:   {_v((room or {}).get('room_type'))}",
            f"Floor:       {_v((room or {}).get('floor'))}",
            f"Zone:        {_v((room or {}).get('zone'))}",
            f"Capacity:    {_v((room or {}).get('capacity'))} guests",
            f"Noise Level: {_v((room or {}).get('noise_level'))}",
            "",
            "Stay Details",
            f"Check-in:        {_v(booking.get('checkin_date'))}",
            f"Check-out:       {_v(booking.get('checkout_date'))}",
            f"Status:          {_v(booking.get('status'), 'confirmed')}",
            f"Booking Source:  {_v(booking.get('booking_source'))}",
            "",
            "Payment Status:  Paid",
            "",
            "Your reservation has been successfully confirmed.",
            "Please contact us if you require any additional services.",
            "---",
        ]
    )


def _build_services_message() -> str:
    services = read_services(_get_sheets_client())
    if not services:
        return "We do not have additional services available at the moment, but I can still assist with any special requests."

    lines = [
        "Absolutely. Here are our available add-on services:",
    ]
    for service in services[:5]:
        name = str(service.get("service_name", "Service"))
        description = str(service.get("description", "")).strip()
        price = service.get("price", "N/A")
        lines.append(f"- {name}: {description} (MYR {price})")

    lines.append("Would you like me to add any of these to your booking?")
    return "\n".join(lines)


def _build_service_selection_response(lowered: str, state) -> str:
    _SERVICE_KEYWORDS = {
        "breakfast": "Breakfast",
        "airport pickup": "Airport Pickup",
        "airport transfer": "Airport Pickup",
        "pickup": "Airport Pickup",
        "late checkout": "Late Checkout",
        "late check-out": "Late Checkout",
        "late check out": "Late Checkout",
        "spa": "Spa",
        "add-on": "Add-on",
        "addon": "Add-on",
    }
    requested = []
    for keyword, label in _SERVICE_KEYWORDS.items():
        if keyword in lowered and label not in requested:
            requested.append(label)

    booking_ref = state.final_booking_id or "your booking"
    if not requested:
        return (
            "Thank you for your interest in our services. "
            "Our concierge team will reach out to confirm your add-ons before your arrival. "
            f"Please reference {booking_ref} when you contact us."
        )

    services_list = " and ".join(requested)
    note = ""
    if "Late Checkout" in requested:
        note = " Regarding late checkout, availability depends on the hotel's occupancy on your departure date — our front desk will confirm the exact hours upon check-in."

    return (
        f"Perfect choice! I have noted your request for {services_list} for {booking_ref}.{note} "
        "Our team will arrange this for your stay and you will receive a confirmation before your arrival. "
        "Is there anything else I can help you with?"
    )


def _missing_profile_fields(state, request: BookingPreviewRequest) -> list[str]:
    profile = state.guest_profile
    missing: list[str] = []

    if not (request.guest_name or profile.get("guest_name")):
        missing.append("guest_name")

    if not (request.stay_purpose or profile.get("stay_purpose")):
        missing.append("stay_purpose")

    if not (profile.get("room_preference") or request.room_type):
        missing.append("room_preference")

    if request.guest_count <= 0 and not profile.get("guest_count"):
        missing.append("guest_count")

    return missing


def _sync_recommended_room_ids_for_preview(state, request: BookingPreviewRequest) -> None:
    """Rebuild recommendation ids from live inventory when session state is stale."""
    available_ids: list[str] = []
    for room in _get_sheets_client().read_all("Rooms"):
        if str(room.get("status", "")).lower() != "available":
            continue

        if request.room_type and str(room.get("room_type", "")).lower() != request.room_type.lower():
            continue

        if int(room.get("capacity", 0) or 0) < request.guest_count:
            continue

        available_ids.append(str(room.get("room_id", "")))

    if available_ids:
        state.recommended_room_ids = available_ids


def _raise_guardrail_error(correlation_id: str, decision) -> None:
    audit_event(
        correlation_id=correlation_id,
        stage=decision.stage,
        action="guardrail_block",
        reason_code=decision.reason_code,
        details={"message": decision.message},
    )
    raise HTTPException(
        status_code=400,
        detail=ErrorResponse(
            correlation_id=correlation_id,
            error=ErrorDetail(
                code="GUARDRAIL_BLOCKED",
                message=decision.message,
                reason_code=decision.reason_code,
            ),
        ).model_dump(),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    correlation_id = uuid4().hex

    input_decision = guardrails.check_input(correlation_id=correlation_id, text=request.message)
    if input_decision.decision == "block":
        _raise_guardrail_error(correlation_id, input_decision)

    policy_decision = guardrails.check_policy(
        correlation_id=correlation_id,
        agent_name="conversation_agent",
        intended_tool=None,
        intent="chat",
    )
    if policy_decision.decision == "block":
        _raise_guardrail_error(correlation_id, policy_decision)

    state = session_manager.get_workflow_state(request.session_id)
    had_guest_name_before = bool(state.guest_profile.get("guest_name"))
    _extract_guest_profile(state, request.message)

    lowered = request.message.lower()
    booking_intent = any(keyword in lowered for keyword in {"book", "reservation", "room"})
    confirm_intent = any(keyword in lowered for keyword in {"confirm booking", "booking confirmed", "booking confirmation", "final confirmation", "confirmed booking"})
    complaint_intent = any(keyword in lowered for keyword in {"complaint", "issue", "dirty", "noise", "problem"})
    services_intent = any(
        keyword in lowered
        for keyword in {"service", "services", "breakfast", "airport", "pickup", "late checkout", "spa", "add-on", "addon"}
    )
    service_selection_intent = services_intent and any(
        keyword in lowered
        for keyword in {"would like", "i want", "please add", "add the", "add ", "i'll have", "i will have", "can i have", "could i have", "get the", "include", "both", "as well", "also"}
    )
    greeting_intent = any(keyword in lowered for keyword in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"})
    has_guest_name = bool(state.guest_profile.get("guest_name"))

    if (
        state.stage == "confirmation"
        and booking_intent
        and not confirm_intent
        and not complaint_intent
        and not services_intent
    ):
        state = session_manager.reset_to_recommendation(request.session_id)

        if has_guest_name:
            session_manager.transition_stage(request.session_id, "profiling")
            return ChatResponse(
                correlation_id=correlation_id,
                session_id=request.session_id,
                response=(
                    f"Absolutely, {state.guest_profile.get('guest_name')}. I can help with a new reservation right away. "
                    "Please share your preferred check-in and check-out dates, guest count, and room type."
                ),
                metadata=_chat_metadata(state),
            )

        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=(
                "Absolutely. I can help with a new reservation right away. "
                "May I have your name so I can prepare your reservation?"
            ),
            metadata=_chat_metadata(state),
        )

    if booking_intent and state.stage == "enquiry":
        session_manager.transition_stage(request.session_id, "profiling")

    if (
        state.stage in {"enquiry", "profiling"}
        and not has_guest_name
        and not confirm_intent
        and (booking_intent or greeting_intent)
    ):
        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=(
                "Welcome to Aurora Nexus Hotel. It is my pleasure to assist you today. "
                "I can help you book a room, explore our services, or handle support requests. "
                "May I have your name so I can prepare your reservation?"
            ),
            metadata=_chat_metadata(state),
        )

    if not had_guest_name_before and has_guest_name and state.stage in {"enquiry", "profiling"}:
        session_manager.transition_stage(request.session_id, "profiling")
        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=(
                f"Wonderful to meet you, {state.guest_profile.get('guest_name')}. "
                "If you are planning a stay with us, could you share your preferred check-in and check-out dates, "
                "as well as the number of guests?"
            ),
            metadata=_chat_metadata(state),
        )

    if state.stage == "profiling" and state.guest_profile.get("guest_name") and state.guest_profile.get("stay_purpose"):
        session_manager.transition_stage(request.session_id, "recommendation")

    if (
        ("confirm booking" in lowered or "booking confirmed" in lowered)
        and state.stage != "confirmation"
    ):
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Cannot confirm booking before successful payment.",
                    reason_code="CONFIRMATION_REQUIRES_PAYMENT",
                ),
            ).model_dump(),
        )

    if confirm_intent and state.stage == "confirmation" and state.payment_confirmed:
        fallback_confirmation = _build_final_confirmation_from_state(state)
        if fallback_confirmation:
            return ChatResponse(
                correlation_id=correlation_id,
                session_id=request.session_id,
                response=fallback_confirmation,
                metadata=_chat_metadata(state),
            )

    if state.stage == "confirmation" and state.payment_confirmed and complaint_intent:
        booking_ref = state.final_booking_id or "your confirmed booking"
        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=(
                "I am sorry to hear that. I can help you file a complaint right away. "
                f"Please share the issue details for {booking_ref}, and I will log it immediately."
            ),
            metadata=_chat_metadata(state),
        )

    if state.stage == "confirmation" and state.payment_confirmed and service_selection_intent:
        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=_build_service_selection_response(lowered, state),
            metadata=_chat_metadata(state),
        )

    if state.stage == "confirmation" and state.payment_confirmed and services_intent:
        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=_build_services_message(),
            metadata=_chat_metadata(state),
        )

    missing_for_recommendation = _profile_missing_for_recommendation(state)
    if state.stage in {"profiling", "recommendation"} and missing_for_recommendation:
        if "guest_count" in missing_for_recommendation:
            return ChatResponse(
                correlation_id=correlation_id,
                session_id=request.session_id,
                response=(
                    f"Thank you, {state.guest_profile.get('guest_name', 'guest')}. "
                    "Before I check availability, may I confirm how many guests will be staying?"
                ),
                metadata=_chat_metadata(state),
            )
        if "stay_dates" in missing_for_recommendation:
            return ChatResponse(
                correlation_id=correlation_id,
                session_id=request.session_id,
                response=(
                    "Wonderful. Please share your check-in and check-out dates so I can check live room availability."
                ),
                metadata=_chat_metadata(state),
            )

    if (
        state.stage in {"profiling", "recommendation"}
        and state.guest_profile.get("guest_name")
        and state.guest_profile.get("stay_purpose")
        and state.guest_profile.get("guest_count")
        and state.guest_profile.get("checkin_date")
        and state.guest_profile.get("checkout_date")
    ):
        if state.stage != "recommendation":
            session_manager.transition_stage(request.session_id, "recommendation")
        recommended_rooms = _recommend_rooms_for_chat(state)
        return ChatResponse(
            correlation_id=correlation_id,
            session_id=request.session_id,
            response=_build_room_recommendation_message(state, recommended_rooms),
            metadata=_chat_metadata(
                state,
                recommended_rooms=[room.model_dump() for room in recommended_rooms],
            ),
        )

    try:
        response_text = await run_agent(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message,
        )
    except Exception as exc:  # noqa: BLE001
        if confirm_intent and state.stage == "confirmation" and state.payment_confirmed:
            fallback_confirmation = _build_final_confirmation_from_state(state)
            quota_error = "resource_exhausted" in str(exc).lower() or "429" in str(exc)
            if fallback_confirmation and quota_error:
                return ChatResponse(
                    correlation_id=correlation_id,
                    session_id=request.session_id,
                    response=fallback_confirmation,
                    metadata=_chat_metadata(state),
                )

        logger.bind(correlation_id=correlation_id, stage="chat").exception(
            "ADK runner failed for session_id={} user_id={}: {}",
            request.session_id,
            request.user_id,
            str(exc),
        )
        settings = get_settings()
        detail_message = "Model runtime failed while processing chat request."
        if settings.app_env.lower() == "development":
            detail_message = f"Model runtime failed while processing chat request: {type(exc).__name__}: {exc}"
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="MODEL_RUNTIME_ERROR",
                    message=detail_message,
                    reason_code="ADK_RUNNER_FAILURE",
                ),
            ).model_dump(),
        ) from exc

    sanitized, output_decision = guardrails.check_output(
        correlation_id=correlation_id,
        text=response_text,
    )

    if state.stage != "confirmation" and _is_premature_confirmation_text(sanitized):
        if state.stage in {"profiling", "recommendation"}:
            recommended_rooms = _recommend_rooms_for_chat(state)
            sanitized = _build_room_recommendation_message(state, recommended_rooms)
        else:
            sanitized = (
                "Your booking is not finalized yet. Please continue with the required stage flow: "
                "room recommendation and selection, booking preview, payment, then final confirmation."
            )

    audit_event(
        correlation_id=correlation_id,
        stage="chat",
        action="chat_completed",
        reason_code=output_decision.reason_code,
        details={"session_id": request.session_id},
    )

    return ChatResponse(
        correlation_id=correlation_id,
        session_id=request.session_id,
        response=sanitized,
        metadata=_chat_metadata(state),
    )


@router.get("/rooms", response_model=RoomsResponse)
async def rooms(query: RoomQuery = Depends()) -> RoomsResponse:
    correlation_id = uuid4().hex

    state = session_manager.get_workflow_state(query.session_id)
    if not state.guest_profile.get("guest_name"):
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="PROFILE_INCOMPLETE",
                    message="Please provide your name before continuing the reservation.",
                    reason_code="PROFILE_STAGE_REQUIRED",
                ),
            ).model_dump(),
        )

    input_decision = guardrails.check_input(correlation_id=correlation_id, text=f"rooms query: {query.room_type or 'any'}")
    if input_decision.decision == "block":
        _raise_guardrail_error(correlation_id, input_decision)

    tool_decision = guardrails.check_tool(
        correlation_id=correlation_id,
        tool_name="find_available_room_tool",
        payload=query.model_dump(),
    )
    if tool_decision.decision == "block":
        _raise_guardrail_error(correlation_id, tool_decision)

    rooms_payload = []
    available_rooms = []
    rooms_all = _get_sheets_client().read_all("Rooms")
    for room in rooms_all:
        if str(room.get("status", "")).lower() != "available":
            continue
        if query.room_type and str(room.get("room_type", "")).lower() != query.room_type.lower():
            continue
        if int(room.get("capacity", 0) or 0) < query.guest_count:
            continue
        available_rooms.append(room)

    available_rooms = sorted(
        available_rooms,
        key=lambda item: _room_rate(str(item.get("room_type", ""))),
    )[:3]

    state.recommended_room_ids = [str(room.get("room_id", "")) for room in available_rooms]
    if state.stage in {"enquiry", "profiling"}:
        session_manager.transition_stage(query.session_id, "recommendation")

    for room in available_rooms:
        rooms_payload.append(
            RoomOption(
                room_id=str(room.get("room_id", "")),
                floor=str(room.get("floor", "")),
                room_type=str(room.get("room_type", "")),
                zone=str(room.get("zone", "")),
                capacity=int(room.get("capacity", 0) or 0),
                price_per_night=_room_rate(str(room.get("room_type", ""))),
                noise_level=str(room.get("noise_level", "")),
                status=str(room.get("status", "")),
                maintenance_status=str(room.get("maintenance_status", "")),
            )
        )

    alternatives = []
    if not rooms_payload:
        alternatives = _build_alternative_date_ranges(query.checkin_date, query.checkout_date)

    return RoomsResponse(
        correlation_id=correlation_id,
        rooms=rooms_payload,
        alternatives=alternatives,
        rooms_checked=len(rooms_all),
    )


@router.post("/booking/preview", response_model=BookingPreviewResponse)
async def booking_preview(request: BookingPreviewRequest) -> BookingPreviewResponse:
    correlation_id = uuid4().hex

    await session_manager.ensure_session(user_id=request.guest_id, session_id=request.session_id)

    state = session_manager.get_workflow_state(request.session_id)

    # Allow a fresh booking cycle after a completed confirmation.
    if state.stage == "confirmation":
        state = session_manager.reset_to_recommendation(request.session_id)

    missing_profile = _missing_profile_fields(state, request)
    if missing_profile:
        missing_name_only = missing_profile == ["guest_name"] or (
            "guest_name" in missing_profile and len(missing_profile) >= 1
        )
        message = (
            "Please provide your name before continuing the reservation."
            if missing_name_only
            else (
                "Guest profiling is required before booking preview. "
                f"Missing: {', '.join(missing_profile)}"
            )
        )
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="PROFILE_INCOMPLETE",
                    message=message,
                    reason_code="PROFILE_STAGE_REQUIRED",
                ),
            ).model_dump(),
        )

    if not state.recommended_room_ids:
        _sync_recommended_room_ids_for_preview(state, request)

    if not state.recommended_room_ids:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Room recommendation is required before booking preview.",
                    reason_code="ROOM_RECOMMENDATION_REQUIRED",
                ),
            ).model_dump(),
        )

    try:
        if state.stage == "recommendation":
            session_manager.transition_stage(request.session_id, "preview")
        elif state.stage != "preview":
            raise ValueError(f"Cannot open booking preview from stage: {state.stage}")
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message=str(exc),
                    reason_code="PREVIEW_STAGE_REQUIRED",
                ),
            ).model_dump(),
        ) from exc

    if state.recommended_room_ids and str(request.room_id) not in state.recommended_room_ids:
        _sync_recommended_room_ids_for_preview(state, request)

    if state.recommended_room_ids and str(request.room_id) not in state.recommended_room_ids:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Please select one of the recommended available rooms before continuing.",
                    reason_code="ROOM_SELECTION_REQUIRED",
                ),
            ).model_dump(),
        )

    selected = [
        r
        for r in _get_sheets_client().read_all("Rooms")
        if str(r.get("room_id", "")) == str(request.room_id)
    ]
    if not selected:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(code="BOOKING_PREVIEW_FAILED", message="Selected room not found."),
            ).model_dump(),
        )

    room = selected[0]
    if str(room.get("status", "")).lower() != "available":
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(code="BOOKING_PREVIEW_FAILED", message="Selected room is not available."),
            ).model_dump(),
        )

    checkin = date.fromisoformat(request.checkin_date)
    checkout = date.fromisoformat(request.checkout_date)
    total_nights = (checkout - checkin).days
    if total_nights <= 0:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(code="BOOKING_PREVIEW_FAILED", message="checkout_date must be after checkin_date."),
            ).model_dump(),
        )

    room_rate = _room_rate(request.room_type)
    total_price = float(room_rate * total_nights)
    guest_name = request.guest_name or str(state.guest_profile.get("guest_name", "")).strip()

    state.selected_room_id = str(request.room_id)
    state.payment_confirmed = False
    state.guest_profile["guest_name"] = guest_name
    state.guest_profile["stay_purpose"] = request.stay_purpose or str(state.guest_profile.get("stay_purpose", ""))
    state.guest_profile["room_preference"] = request.room_type
    state.guest_profile["guest_count"] = request.guest_count
    state.booking_preview = {
        "guest_name": guest_name,
        "room_id": str(request.room_id),
        "room_type": request.room_type,
        "checkin_date": request.checkin_date,
        "checkout_date": request.checkout_date,
        "guest_count": request.guest_count,
        "total_nights": total_nights,
        "total_price": total_price,
        "currency": "MYR",
    }

    return BookingPreviewResponse(
        correlation_id=correlation_id,
        guest_name=guest_name,
        room_id=str(request.room_id),
        room_type=request.room_type,
        checkin_date=request.checkin_date,
        checkout_date=request.checkout_date,
        guest_count=request.guest_count,
        total_nights=total_nights,
        total_price=total_price,
    )


@router.post("/booking/preview/cancel", response_model=StageTransitionResponse)
async def booking_preview_cancel(request: BookingPreviewCancelRequest) -> StageTransitionResponse:
    correlation_id = uuid4().hex
    await session_manager.ensure_session(user_id=request.guest_id, session_id=request.session_id)

    state = session_manager.reset_to_recommendation(request.session_id)
    return StageTransitionResponse(
        correlation_id=correlation_id,
        stage=state.stage,
        message="Booking preview cancelled. Returning to room recommendation stage.",
    )


@router.post("/booking", response_model=BookingResponse)
async def booking(request: BookingRequest) -> BookingResponse:
    correlation_id = uuid4().hex

    await session_manager.ensure_session(user_id=request.guest_id, session_id=request.session_id)
    state = session_manager.get_workflow_state(request.session_id)

    if state.stage != "preview":
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Booking confirmation requires /booking/preview first.",
                    reason_code="PREVIEW_REQUIRED",
                ),
            ).model_dump(),
        )

    if state.selected_room_id and request.room_id and str(state.selected_room_id) != str(request.room_id):
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Selected room does not match the active booking preview.",
                    reason_code="ROOM_SELECTION_MISMATCH",
                ),
            ).model_dump(),
        )

    if not request.room_id:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Please select a recommended room before creating a booking.",
                    reason_code="ROOM_SELECTION_REQUIRED",
                ),
            ).model_dump(),
        )

    input_decision = guardrails.check_input(correlation_id=correlation_id, text=f"booking for guest {request.guest_id}")
    if input_decision.decision == "block":
        _raise_guardrail_error(correlation_id, input_decision)

    policy_decision = guardrails.check_policy(
        correlation_id=correlation_id,
        agent_name="reservation_agent",
        intended_tool="create_booking_tool",
        intent="booking",
    )
    if policy_decision.decision == "block":
        _raise_guardrail_error(correlation_id, policy_decision)

    tool_decision = guardrails.check_tool(
        correlation_id=correlation_id,
        tool_name="create_booking_tool",
        payload=request.model_dump(),
    )
    if tool_decision.decision == "block":
        _raise_guardrail_error(correlation_id, tool_decision)

    try:
        room = None
        if request.room_id:
            selected = [
                r
                for r in _get_sheets_client().read_all("Rooms")
                if str(r.get("room_id", "")) == str(request.room_id)
            ]
            if not selected:
                raise SheetValidationError(f"Selected room not found: {request.room_id}")
            room = selected[0]

            if str(room.get("status", "")).lower() != "available":
                raise SheetValidationError("Selected room is not available")
            if str(room.get("room_type", "")).lower() != request.room_type.lower():
                raise SheetValidationError("Selected room type does not match requested room_type")
            if int(room.get("capacity", 0) or 0) < request.guest_count:
                raise SheetValidationError("Selected room does not satisfy guest capacity")
        if not room:
            raise SheetValidationError("No available room found for requested constraints")

        booking_payload = create_booking(
            _get_sheets_client(),
            guest_id=request.guest_id,
            room_id=str(room["room_id"]),
            checkin_date=request.checkin_date,
            checkout_date=request.checkout_date,
            booking_source=request.booking_source,
        )
    except SheetValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(code="BOOKING_FAILED", message=str(exc)),
            ).model_dump(),
        ) from exc

    state.final_booking_id = booking_payload["booking_id"]
    state.payment_preview = {}
    session_manager.transition_stage(request.session_id, "payment")

    return BookingResponse(
        correlation_id=correlation_id,
        booking_id=booking_payload["booking_id"],
        room_id=booking_payload["room_id"],
        checkin_date=booking_payload["checkin_date"],
        checkout_date=booking_payload["checkout_date"],
        booking_status=booking_payload["status"],
    )


@router.post("/payment/preview", response_model=PaymentPreviewResponse)
async def payment_preview(request: PaymentPreviewRequest) -> PaymentPreviewResponse:
    correlation_id = uuid4().hex
    state = session_manager.get_workflow_state(request.session_id)

    if state.stage != "payment":
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Payment preview is only available after booking confirmation.",
                    reason_code="PAYMENT_STAGE_REQUIRED",
                ),
            ).model_dump(),
        )

    if state.final_booking_id and str(state.final_booking_id) != str(request.booking_id):
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="booking_id does not match the active booking for this session.",
                    reason_code="BOOKING_CONTEXT_MISMATCH",
                ),
            ).model_dump(),
        )

    amount = float(state.booking_preview.get("total_price", 0.0) or 0.0)
    if amount <= 0:
        total_nights = int(state.booking_preview.get("total_nights", 1) or 1)
        room_type = str(state.booking_preview.get("room_type", "Deluxe"))
        amount = float(_room_rate(room_type) * total_nights)

    state.payment_preview = {"amount": amount, "booking_id": request.booking_id}

    return PaymentPreviewResponse(
        correlation_id=correlation_id,
        booking_id=request.booking_id,
        amount=amount,
    )


@router.post("/payment/cancel", response_model=StageTransitionResponse)
async def payment_cancel(request: PaymentCancelRequest) -> StageTransitionResponse:
    correlation_id = uuid4().hex
    state = session_manager.get_workflow_state(request.session_id)

    if state.stage != "payment":
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Payment cancellation is only available during payment stage.",
                    reason_code="PAYMENT_STAGE_REQUIRED",
                ),
            ).model_dump(),
        )

    session_manager.transition_stage(request.session_id, "preview")
    state.payment_preview = {}
    state.payment_confirmed = False

    return StageTransitionResponse(
        correlation_id=correlation_id,
        stage=state.stage,
        message="Payment cancelled. Returning to booking preview stage.",
    )


@router.post("/payment", response_model=PaymentResponse)
async def payment(request: PaymentRequest) -> PaymentResponse:
    correlation_id = uuid4().hex

    state = session_manager.get_workflow_state(request.session_id)
    if state.stage != "payment":
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="INVALID_STAGE_TRANSITION",
                    message="Cannot process payment before booking confirmation stage.",
                    reason_code="PAYMENT_STAGE_REQUIRED",
                ),
            ).model_dump(),
        )

    preview_amount = float(state.payment_preview.get("amount", 0.0) or 0.0)
    if preview_amount > 0 and abs(preview_amount - float(request.amount)) > 0.01:
        raise HTTPException(
            status_code=409,
            detail=ErrorResponse(
                correlation_id=correlation_id,
                error=ErrorDetail(
                    code="PAYMENT_AMOUNT_MISMATCH",
                    message="Payment amount does not match payment preview total.",
                    reason_code="PAYMENT_PREVIEW_MISMATCH",
                ),
            ).model_dump(),
        )

    input_decision = guardrails.check_input(correlation_id=correlation_id, text=f"payment for booking {request.booking_id}")
    if input_decision.decision == "block":
        _raise_guardrail_error(correlation_id, input_decision)

    policy_decision = guardrails.check_policy(
        correlation_id=correlation_id,
        agent_name="billing_agent",
        intended_tool="log_payment_tool",
        intent="payment",
    )
    if policy_decision.decision == "block":
        _raise_guardrail_error(correlation_id, policy_decision)

    tool_decision = guardrails.check_tool(
        correlation_id=correlation_id,
        tool_name="log_payment_tool",
        payload=request.model_dump(),
    )
    if tool_decision.decision == "block":
        _raise_guardrail_error(correlation_id, tool_decision)

    payment_payload = log_payment(
        _get_sheets_client(),
        booking_id=request.booking_id,
        guest_id=request.guest_id,
        amount=request.amount,
        payment_status=request.payment_status,
        transaction_id=request.transaction_id,
    )

    update_booking_status(
        _get_sheets_client(),
        booking_id=request.booking_id,
        status="confirmed",
    )

    state.payment_confirmed = True
    session_manager.transition_stage(request.session_id, "confirmation")

    return PaymentResponse(
        correlation_id=correlation_id,
        payment_id=payment_payload["payment_id"],
        payment_status=payment_payload["payment_status"],
        stage="confirmation",
    )


@router.post("/complaint", response_model=ComplaintResponse)
async def complaint(request: ComplaintRequest) -> ComplaintResponse:
    correlation_id = uuid4().hex

    input_decision = guardrails.check_input(correlation_id=correlation_id, text=request.issue)
    if input_decision.decision == "block":
        _raise_guardrail_error(correlation_id, input_decision)

    policy_decision = guardrails.check_policy(
        correlation_id=correlation_id,
        agent_name="support_agent",
        intended_tool="log_complaint_tool",
        intent="complaint",
    )
    if policy_decision.decision == "block":
        _raise_guardrail_error(correlation_id, policy_decision)

    tool_decision = guardrails.check_tool(
        correlation_id=correlation_id,
        tool_name="log_complaint_tool",
        payload=request.model_dump(),
    )
    if tool_decision.decision == "block":
        _raise_guardrail_error(correlation_id, tool_decision)

    payload = log_complaint(
        _get_sheets_client(),
        guest_id=request.guest_id,
        booking_id=request.booking_id or "",
        issue=request.issue,
        resolution=request.resolution,
    )

    status_detail = "Complaint logged successfully"
    if request.booking_id:
        try:
            reassignment = reassign_room_for_complaint(
                _get_sheets_client(),
                guest_id=request.guest_id,
                booking_id=request.booking_id,
                issue=request.issue,
            )
            if reassignment.get("changed"):
                status_detail = (
                    "Complaint logged and room reassigned "
                    f"from {reassignment['old_room_id']} to {reassignment['new_room_id']}"
                )
            elif reassignment.get("reason"):
                status_detail = f"Complaint logged. {reassignment['reason']}"
        except SheetValidationError as exc:
            status_detail = f"Complaint logged. Room reassignment not applied: {exc}"

    return ComplaintResponse(
        correlation_id=correlation_id,
        complaint_id=payload["complaint_id"],
        status_detail=status_detail,
    )
