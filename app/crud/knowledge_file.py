from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client


async def get_knowledge_files(client: Client, property_id: str) -> list[dict]:
    response = (
        client.table("knowledge_files")
        .select("*")
        .eq("property_id", property_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


async def create_knowledge_file(client: Client, property_id: str, data: dict) -> dict:
    row = {"property_id": property_id, **data}
    response = client.table("knowledge_files").insert(row).execute()
    return response.data[0]


async def delete_knowledge_file(client: Client, file_id: str, user_id: str) -> bool:
    response = (
        client.table("knowledge_files")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": user_id})
        .eq("id", file_id)
        .execute()
    )
    return bool(response.data)
