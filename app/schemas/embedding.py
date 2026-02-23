from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(10, ge=1, le=50)
    threshold: float = Field(0.7, ge=0.0, le=1.0)


class EmbeddingSearchResult(BaseModel):
    id: str
    source_type: str
    source_id: str
    content: str
    similarity: float
    metadata: dict = {}


class EmbeddingSearchResponse(BaseModel):
    results: list[EmbeddingSearchResult]
    query: str


class EmbeddingStatusResponse(BaseModel):
    total: int = 0
    by_source: dict[str, int] = {}


class EmbeddingGenerateResponse(BaseModel):
    property_embeddings: int = 0
    room_embeddings: int = 0
    total: int = 0
