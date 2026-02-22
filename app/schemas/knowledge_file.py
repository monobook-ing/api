from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeFileCreate(BaseModel):
    name: str = Field(..., min_length=1)
    size: str = "0 KB"
    storage_path: str | None = None
    mime_type: str | None = None


class KnowledgeFileResponse(BaseModel):
    id: str
    property_id: str
    name: str
    size: str
    storage_path: str | None = None
    mime_type: str | None = None
    created_at: datetime


class KnowledgeFileListResponse(BaseModel):
    items: list[KnowledgeFileResponse]
