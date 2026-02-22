from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    property_id: str
    conversation_id: str | None = None
    source: str
    tool_name: str
    description: str
    status: str
    request_payload: dict | None = None
    response_payload: dict | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    next_cursor: str | None = None
