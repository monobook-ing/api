from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    guest_name: str | None = None
    guest_email: str | None = None
    source: str = "widget"


class ChatSessionResponse(BaseModel):
    id: str
    property_id: str
    guest_name: str | None = None
    guest_email: str | None = None
    source: str
    created_at: datetime


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    tool_calls: dict | list | None = None
    metadata: dict = {}
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
