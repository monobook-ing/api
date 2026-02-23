from __future__ import annotations

from supabase import Client


async def create_session(
    client: Client,
    property_id: str,
    source: str = "widget",
    guest_name: str | None = None,
    guest_email: str | None = None,
) -> dict:
    row = {
        "property_id": property_id,
        "source": source,
    }
    if guest_name:
        row["guest_name"] = guest_name
    if guest_email:
        row["guest_email"] = guest_email

    response = client.table("chat_sessions").insert(row).execute()
    return response.data[0]


async def get_session(client: Client, session_id: str) -> dict | None:
    response = (
        client.table("chat_sessions")
        .select("*")
        .eq("id", session_id)
        .execute()
    )
    return response.data[0] if response.data else None


async def create_message(
    client: Client,
    session_id: str,
    role: str,
    content: str,
    tool_calls: dict | list | None = None,
    metadata: dict | None = None,
) -> dict:
    row = {
        "session_id": session_id,
        "role": role,
        "content": content,
    }
    if tool_calls:
        row["tool_calls"] = tool_calls
    if metadata:
        row["metadata"] = metadata

    response = client.table("chat_messages").insert(row).execute()
    return response.data[0]


async def get_messages(
    client: Client, session_id: str, limit: int = 50
) -> list[dict]:
    response = (
        client.table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return response.data or []
