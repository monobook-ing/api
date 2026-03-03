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


async def get_knowledge_file_content(client: Client, file_id: str) -> list[dict]:
    response = (
        client.table("embeddings")
        .select("content, chunk_index, metadata")
        .eq("source_type", "knowledge_chunk")
        .eq("source_id", file_id)
        .order("chunk_index")
        .execute()
    )
    return response.data or []


async def delete_knowledge_file(client: Client, file_id: str, user_id: str) -> bool:
    response = (
        client.table("knowledge_files")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": user_id})
        .eq("id", file_id)
        .execute()
    )
    return bool(response.data)


async def get_next_pending_file(client: Client) -> dict | None:
    """Claim and return the next pending knowledge file for indexing."""
    try:
        response = client.rpc("claim_next_pending_knowledge_file").execute()
        rows = response.data or []
        return rows[0] if rows else None
    except Exception:
        # Fallback path when migration has not been applied yet.
        response = (
            client.table("knowledge_files")
            .select("*")
            .eq("indexing_status", "pending")
            .is_("deleted_at", "null")
            .neq("storage_path", "")
            .order("created_at")
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
