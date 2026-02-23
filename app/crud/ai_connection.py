from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client

from app.services.encryption import decrypt_api_key, encrypt_api_key


async def get_ai_connections(client: Client, property_id: str) -> list[dict]:
    response = (
        client.table("ai_connections")
        .select("*")
        .eq("property_id", property_id)
        .execute()
    )
    results = []
    for row in response.data or []:
        row["has_api_key"] = bool(row.get("api_key_encrypted"))
        row.pop("api_key_encrypted", None)
        results.append(row)
    return results


async def upsert_ai_connection(
    client: Client, property_id: str, provider: str, data: dict
) -> dict:
    # Prepare update payload
    payload: dict = {
        "enabled": data["enabled"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if data.get("model_id") is not None:
        payload["model_id"] = data["model_id"]
    if data.get("api_key"):
        payload["api_key_encrypted"] = encrypt_api_key(data["api_key"])

    # Check if exists
    existing = (
        client.table("ai_connections")
        .select("id")
        .eq("property_id", property_id)
        .eq("provider", provider)
        .execute()
    )

    if existing.data:
        response = (
            client.table("ai_connections")
            .update(payload)
            .eq("property_id", property_id)
            .eq("provider", provider)
            .execute()
        )
    else:
        payload["property_id"] = property_id
        payload["provider"] = provider
        response = client.table("ai_connections").insert(payload).execute()

    row = response.data[0]
    row["has_api_key"] = bool(row.get("api_key_encrypted"))
    row.pop("api_key_encrypted", None)
    return row


async def get_decrypted_api_key(
    client: Client, property_id: str, provider: str = "openai"
) -> str | None:
    """Retrieve and decrypt the API key for a property's AI provider."""
    response = (
        client.table("ai_connections")
        .select("api_key_encrypted, enabled")
        .eq("property_id", property_id)
        .eq("provider", provider)
        .eq("enabled", True)
        .execute()
    )
    if not response.data:
        return None
    encrypted = response.data[0].get("api_key_encrypted")
    if not encrypted:
        return None
    return decrypt_api_key(encrypted)
