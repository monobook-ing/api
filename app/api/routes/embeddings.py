from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.core.config import get_settings
from app.crud.ai_connection import get_decrypted_api_key
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.embedding import (
    EmbeddingGenerateResponse,
    EmbeddingSearchRequest,
    EmbeddingSearchResponse,
    EmbeddingSearchResult,
    EmbeddingStatusResponse,
)
from app.services.embedding import embed_all_rooms, embed_property, search_similar

router = APIRouter(
    prefix="/v1.0/properties/{property_id}/embeddings", tags=["embeddings"]
)

settings = get_settings()


async def _get_api_key(client: Client, property_id: str) -> str:
    """Get OpenAI API key: property-level first, then fallback to platform key."""
    key = await get_decrypted_api_key(client, property_id, "openai")
    if key:
        return key
    if settings.openai_api_key:
        return settings.openai_api_key
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No OpenAI API key configured. Add one in AI Provider settings.",
    )


@router.post("/generate", response_model=EmbeddingGenerateResponse)
async def generate_embeddings(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Generate embeddings for a property and all its active rooms."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    api_key = await _get_api_key(client, property_id)

    prop_count = await embed_property(client, property_id, api_key)
    room_count = await embed_all_rooms(client, property_id, api_key)

    return EmbeddingGenerateResponse(
        property_embeddings=prop_count,
        room_embeddings=room_count,
        total=prop_count + room_count,
    )


@router.post("/search", response_model=EmbeddingSearchResponse)
async def search_embeddings(
    property_id: str,
    payload: EmbeddingSearchRequest,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Semantic search across property embeddings."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    api_key = await _get_api_key(client, property_id)

    results = await search_similar(
        client, property_id, payload.query, api_key, payload.limit, payload.threshold
    )
    return EmbeddingSearchResponse(
        results=[EmbeddingSearchResult(**r) for r in results],
        query=payload.query,
    )


@router.get("/status", response_model=EmbeddingStatusResponse)
async def embedding_status(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get embedding statistics for a property."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    response = (
        client.table("embeddings")
        .select("source_type")
        .eq("property_id", property_id)
        .execute()
    )
    rows = response.data or []
    by_source: dict[str, int] = {}
    for r in rows:
        st = r["source_type"]
        by_source[st] = by_source.get(st, 0) + 1

    return EmbeddingStatusResponse(total=len(rows), by_source=by_source)
