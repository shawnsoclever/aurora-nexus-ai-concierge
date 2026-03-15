from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    status: str = Field(default="success")
    correlation_id: str


class ChatRequest(BaseModel):
    session_id: str
    user_id: str
    message: str


class ChatResponse(ApiResponse):
    session_id: str
    response: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BookingRequest(BaseModel):
    session_id: str
    guest_id: str
    checkin_date: str
    checkout_date: str
    room_type: str
    room_id: str | None = None
    guest_count: int = Field(gt=0)
    booking_source: str = "direct"


class BookingPreviewRequest(BaseModel):
    session_id: str
    guest_id: str
    guest_name: str | None = None
    stay_purpose: str | None = None
    checkin_date: str
    checkout_date: str
    room_type: str
    room_id: str
    guest_count: int = Field(gt=0)


class BookingPreviewResponse(ApiResponse):
    guest_name: str
    room_id: str
    room_type: str
    checkin_date: str
    checkout_date: str
    guest_count: int
    total_nights: int
    total_price: float
    currency: str = "MYR"
    stage: str = "preview"


class BookingResponse(ApiResponse):
    booking_id: str
    room_id: str
    checkin_date: str
    checkout_date: str
    booking_status: str


class BookingPreviewCancelRequest(BaseModel):
    session_id: str
    guest_id: str


class PaymentCancelRequest(BaseModel):
    session_id: str


class StageTransitionResponse(ApiResponse):
    stage: str
    message: str


class RoomQuery(BaseModel):
    session_id: str = "rooms-session"
    user_id: str = "rooms-user"
    checkin_date: str
    checkout_date: str
    guest_count: int = Field(gt=0)
    room_type: str | None = None


class RoomOption(BaseModel):
    room_id: str
    floor: str
    room_type: str
    zone: str
    capacity: int
    price_per_night: float
    noise_level: str
    status: str
    maintenance_status: str


class RoomsResponse(ApiResponse):
    rooms: list[RoomOption]
    alternatives: list[str] = Field(default_factory=list)
    rooms_checked: int = 0


class PaymentRequest(BaseModel):
    session_id: str
    user_id: str = "billing-user"
    booking_id: str
    guest_id: str
    amount: float = Field(gt=0)
    payment_status: str = "success"
    transaction_id: str


class PaymentPreviewRequest(BaseModel):
    session_id: str
    booking_id: str


class PaymentPreviewResponse(ApiResponse):
    booking_id: str
    amount: float
    currency: str = "MYR"
    payment_status: str = "pending"
    stage: str = "payment"


class PaymentResponse(ApiResponse):
    payment_id: str
    payment_status: str
    stage: str = "confirmation"


class ComplaintRequest(BaseModel):
    session_id: str
    user_id: str = "support-user"
    booking_id: str | None = None
    guest_id: str
    issue: str
    resolution: str = ""


class ComplaintResponse(ApiResponse):
    complaint_id: str
    status_detail: str
