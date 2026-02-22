from __future__ import annotations

from supabase import Client


async def get_host_profile(client: Client, property_id: str) -> dict | None:
    response = (
        client.table("host_profiles")
        .select("*")
        .eq("property_id", property_id)
        .execute()
    )
    if response.data:
        return response.data[0]
    return None


async def upsert_host_profile(client: Client, property_id: str, data: dict) -> dict:
    existing = await get_host_profile(client, property_id)
    if existing:
        filtered = {k: v for k, v in data.items() if v is not None}
        response = (
            client.table("host_profiles")
            .update(filtered)
            .eq("property_id", property_id)
            .execute()
        )
        return response.data[0]
    else:
        row = {"property_id": property_id, **{k: v for k, v in data.items() if v is not None}}
        response = client.table("host_profiles").insert(row).execute()
        return response.data[0]
