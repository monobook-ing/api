from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PropertyAddressUpdate(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    lat: float | None = None
    lng: float | None = None
    floor: str | None = None
    section: str | None = None
    property_number: str | None = None


class PropertyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    address: PropertyAddressUpdate | None = None
    description: str | None = None
    image_url: str | None = None


class PropertyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    image_url: str | None = None
    rating: float | None = None
    ai_match_score: int | None = None
    address: PropertyAddressUpdate | None = None


class PropertyResponse(BaseModel):
    id: str
    account_id: str
    name: str
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    lat: float | None = None
    lng: float | None = None
    floor: str | None = None
    section: str | None = None
    property_number: str | None = None
    description: str | None = None
    image_url: str | None = None
    rating: float | None = 0
    ai_match_score: int | None = 0
    created_at: datetime
    updated_at: datetime


class PropertyListResponse(BaseModel):
    items: list[PropertyResponse]
