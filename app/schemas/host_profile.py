from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HostProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    location: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    avatar_initials: str | None = None
    reviews: int | None = None
    rating: float | None = None
    years_hosting: int | None = None
    superhost: bool | None = None


class HostProfileResponse(BaseModel):
    id: str
    property_id: str
    name: str
    location: str
    bio: str
    avatar_url: str | None = None
    avatar_initials: str
    reviews: int
    rating: float
    years_hosting: int
    superhost: bool
    created_at: datetime
    updated_at: datetime
