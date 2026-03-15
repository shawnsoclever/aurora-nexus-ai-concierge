from pydantic import ValidationError

from api.schemas import BookingRequest, ChatRequest, PaymentRequest


def test_chat_schema() -> None:
    req = ChatRequest(session_id="s1", user_id="u1", message="hello")
    assert req.session_id == "s1"


def test_booking_checkout_validation() -> None:
    """checkout_date same as checkin_date is valid at schema level; tool_guard catches it."""
    req = BookingRequest(
        session_id="s1",
        guest_id="g1",
        checkin_date="2026-03-20",
        checkout_date="2026-03-22",
        room_type="Deluxe",
        guest_count=2,
        booking_source="direct",
    )
    assert req.checkin_date == "2026-03-20"
    assert req.checkout_date == "2026-03-22"


def test_booking_guest_count_validation() -> None:
    try:
        BookingRequest(
            session_id="s1",
            guest_id="g1",
            checkin_date="2026-03-20",
            checkout_date="2026-03-22",
            room_type="Deluxe",
            guest_count=0,
        )
        assert False, "Expected ValidationError"
    except ValidationError:
        assert True


def test_payment_amount_validation() -> None:
    try:
        PaymentRequest(
            session_id="s1",
            booking_id="b1",
            guest_id="g1",
            amount=0,
            transaction_id="txn-abc",
        )
        assert False, "Expected ValidationError"
    except ValidationError:
        assert True
