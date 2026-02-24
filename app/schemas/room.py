from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GuestTierCreate(BaseModel):
    min_guests: int = Field(..., ge=1)
    max_guests: int = Field(..., ge=1)
    price_per_night: float = Field(..., gt=0)


class DatePriceOverride(BaseModel):
    date: str  # YYYY-MM-DD
    price: float = Field(..., gt=0)


class RoomImportRequest(BaseModel):
    url: str = Field(..., min_length=1)


class RoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1)
    description: str = ""
    images: list[str] = []
    price_per_night: float = Field(..., gt=0)
    max_guests: int = Field(2, ge=1)
    bed_config: str = ""
    amenities: list[str] = []
    source: str = "manual"
    source_url: str | None = None
    sync_enabled: bool = False
    status: str = "active"


class RoomUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    type: str | None = None
    description: str | None = None
    images: list[str] | None = None
    price_per_night: float | None = Field(None, gt=0)
    max_guests: int | None = Field(None, ge=1)
    bed_config: str | None = None
    amenities: list[str] | None = None
    source: str | None = None
    source_url: str | None = None
    sync_enabled: bool | None = None
    status: str | None = None


class RoomPricingUpdate(BaseModel):
    date_overrides: list[DatePriceOverride] = []
    guest_tiers: list[GuestTierCreate] = []


class GuestTierResponse(BaseModel):
    id: str
    min_guests: int
    max_guests: int
    price_per_night: float


class DatePriceResponse(BaseModel):
    id: str
    date: str
    price: float


class RoomResponse(BaseModel):
    id: str
    property_id: str
    name: str
    type: str
    description: str
    images: list[str]
    price_per_night: float
    max_guests: int
    bed_config: str
    amenities: list[str]
    source: str
    source_url: str | None = None
    sync_enabled: bool
    last_synced: datetime | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    guest_tiers: list[GuestTierResponse] = []
    date_overrides: list[DatePriceResponse] = []


class RoomListResponse(BaseModel):
    items: list[RoomResponse]
