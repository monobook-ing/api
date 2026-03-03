from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CuratedPlaceCreate(BaseModel):
    google_place_id: str | None = None
    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    cuisine: list[str] = Field(default_factory=list)
    price_level: int | None = Field(default=None, ge=0, le=4)
    rating: float | None = None
    review_count: int | None = Field(default=None, ge=0)
    phone: str | None = None
    website: str | None = None
    photo_urls: list[str] = Field(default_factory=list)
    opening_hours: dict | None = None
    meal_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)
    walking_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = None
    sponsored: bool = False
    sort_order: int = 0
    verified: bool = False


class CuratedPlaceUpdate(BaseModel):
    google_place_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    cuisine: list[str] | None = None
    price_level: int | None = Field(default=None, ge=0, le=4)
    rating: float | None = None
    review_count: int | None = Field(default=None, ge=0)
    phone: str | None = None
    website: str | None = None
    photo_urls: list[str] | None = None
    opening_hours: dict | None = None
    meal_types: list[str] | None = None
    tags: list[str] | None = None
    best_for: list[str] | None = None
    walking_minutes: int | None = Field(default=None, ge=0)
    notes: str | None = None
    sponsored: bool | None = None
    sort_order: int | None = None
    verified: bool | None = None


class CuratedPlaceImport(BaseModel):
    google_place_id: str = Field(..., min_length=1)
    force: bool = False


class CuratedPlaceResponse(BaseModel):
    id: str
    property_id: str
    google_place_id: str | None = None
    name: str
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    cuisine: list[str] = Field(default_factory=list)
    price_level: int | None = None
    rating: float | None = None
    review_count: int | None = None
    phone: str | None = None
    website: str | None = None
    photo_urls: list[str] = Field(default_factory=list)
    opening_hours: dict | None = None
    meal_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)
    walking_minutes: int | None = None
    notes: str | None = None
    sponsored: bool = False
    sort_order: int = 0
    verified: bool = False
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by: str | None = None


class CuratedPlaceListResponse(BaseModel):
    items: list[CuratedPlaceResponse]
