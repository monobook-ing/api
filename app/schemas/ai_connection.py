from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIConnectionUpsert(BaseModel):
    enabled: bool
    api_key: str | None = None
    model_id: str | None = None


class AIConnectionResponse(BaseModel):
    id: str
    property_id: str
    provider: str
    enabled: bool
    model_id: str | None = None
    has_api_key: bool = False
    config: dict = {}
    created_at: datetime
    updated_at: datetime


class AIConnectionListResponse(BaseModel):
    items: list[AIConnectionResponse]


class AIConnectionTestResponse(BaseModel):
    success: bool
    message: str
