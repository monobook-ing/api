from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAI
from supabase import Client

from app.api import deps
from app.crud.ai_connection import get_ai_connections, get_decrypted_api_key, upsert_ai_connection
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.ai_connection import (
    AIConnectionListResponse,
    AIConnectionResponse,
    AIConnectionTestResponse,
    AIConnectionUpsert,
)

router = APIRouter(
    prefix="/v1.0/properties/{property_id}/ai-connections", tags=["ai-connections"]
)


async def _check_access(client: Client, user_id: str, property_id: str):
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("", response_model=AIConnectionListResponse)
async def list_ai_connections(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """List AI provider connections for a property."""
    await _check_access(client, current_user["id"], property_id)
    rows = await get_ai_connections(client, property_id)
    return AIConnectionListResponse(items=rows)


@router.put("/{provider}", response_model=AIConnectionResponse)
async def update_ai_connection(
    property_id: str,
    provider: str,
    payload: AIConnectionUpsert,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Create or update an AI provider connection (toggle + API key)."""
    await _check_access(client, current_user["id"], property_id)

    valid_providers = ("openai", "claude", "google")
    if provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}",
        )

    row = await upsert_ai_connection(client, property_id, provider, payload.model_dump())
    return row


@router.post("/{provider}/test", response_model=AIConnectionTestResponse)
async def test_ai_connection(
    property_id: str,
    provider: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Test that a stored AI provider API key is valid."""
    await _check_access(client, current_user["id"], property_id)

    api_key = await get_decrypted_api_key(client, property_id, provider)
    if not api_key:
        return AIConnectionTestResponse(
            success=False, message="No API key configured or provider not enabled"
        )

    try:
        if provider == "openai":
            openai_client = OpenAI(api_key=api_key)
            openai_client.models.list()
            return AIConnectionTestResponse(success=True, message="OpenAI connection successful")
        else:
            return AIConnectionTestResponse(
                success=False, message=f"Provider '{provider}' test not implemented yet"
            )
    except Exception as e:
        return AIConnectionTestResponse(success=False, message=f"Connection failed: {str(e)}")
