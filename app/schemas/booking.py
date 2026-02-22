from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class BookingCreate(BaseModel):
    room_id: str
    guest_name: str = Field(..., min_length=1)
    guest_email: str | None = None
    guest_phone: str | None = None
    check_in: date
    check_out: date
    total_price: float = Field(..., gt=0)
    status: str = "pending"
    ai_handled: bool = False
    source: str | None = None
    conversation_id: str | None = None


class BookingUpdate(BaseModel):
    check_in: date | None = None
    check_out: date | None = None
    total_price: float | None = Field(None, gt=0)
    status: str | None = None


class BookingResponse(BaseModel):
    id: str
    property_id: str
    room_id: str
    guest_id: str
    guest_name: str | None = None
    check_in: date
    check_out: date
    total_price: float
    status: str
    ai_handled: bool
    source: str | None = None
    conversation_id: str | None = None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None


class BookingListResponse(BaseModel):
    items: list[BookingResponse]
