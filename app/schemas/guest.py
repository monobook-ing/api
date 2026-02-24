from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GuestLatestBookingResponse(BaseModel):
    id: str
    room_id: str
    room_image: str | None = None
    room_name: str
    check_in: date
    check_out: date
    status: str
    total_price: float
    ai_handled: bool
    source: str | None = None


class GuestSummaryResponse(BaseModel):
    id: str
    property_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    notes: str
    total_stays: int
    last_stay_date: date | None = None
    total_spent: float
    latest_booking: GuestLatestBookingResponse | None = None
    created_at: datetime
    updated_at: datetime


class GuestBookingResponse(BaseModel):
    id: str
    guest_id: str
    room_id: str
    room_name: str
    property_id: str
    check_in: date
    check_out: date
    status: str
    total_price: float
    ai_handled: bool
    source: str | None = None
    conversation_id: str | None = None


class ConversationMessageResponse(BaseModel):
    role: Literal["guest", "ai"]
    text: str
    timestamp: datetime


class GuestConversationResponse(BaseModel):
    id: str
    guest_id: str | None = None
    channel: str
    started_at: datetime
    messages: list[ConversationMessageResponse] = Field(default_factory=list)


class GuestDetailResponse(GuestSummaryResponse):
    bookings: list[GuestBookingResponse] = Field(default_factory=list)
    conversations: list[GuestConversationResponse] = Field(default_factory=list)


class GuestListResponse(BaseModel):
    items: list[GuestSummaryResponse]


class GuestUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: str | None = Field(None, max_length=320)
    phone: str | None = Field(None, max_length=64)
    notes: str | None = Field(None, max_length=4000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("email", "phone")
    @classmethod
    def normalize_optional_contact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()
