from __future__ import annotations

from datetime import date, datetime

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
    language: str = "en"
    doc_type: str = "general"
    effective_date: date | None = None
    indexing_status: str = "pending"
    chunk_count: int = 0
    extraction_error: str | None = None
    created_at: datetime


class KnowledgeFileListResponse(BaseModel):
    items: list[KnowledgeFileResponse]
