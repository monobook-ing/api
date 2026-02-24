from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client


async def create_session(
    client: Client,
    property_id: str,
    source: str = "widget",
    guest_id: str | None = None,
    guest_name: str | None = None,
    guest_email: str | None = None,
) -> dict:
    row = {
        "property_id": property_id,
        "source": source,
    }
    if guest_id:
        row["guest_id"] = guest_id
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


async def resolve_guest_id(
    client: Client,
    property_id: str,
    guest_id: str | None = None,
    guest_name: str | None = None,
    guest_email: str | None = None,
) -> str | None:
    if guest_id:
        by_id = (
            client.table("guests")
            .select("id")
            .eq("id", guest_id)
            .eq("property_id", property_id)
            .limit(1)
            .execute()
        )
        if by_id.data:
            return by_id.data[0]["id"]
        return None

    if guest_email:
        by_email = (
            client.table("guests")
            .select("id")
            .eq("property_id", property_id)
            .ilike("email", guest_email.strip())
            .limit(1)
            .execute()
        )
        if by_email.data:
            return by_email.data[0]["id"]

    if guest_name:
        by_name = (
            client.table("guests")
            .select("id")
            .eq("property_id", property_id)
            .ilike("name", guest_name.strip())
            .limit(1)
            .execute()
        )
        if by_name.data:
            return by_name.data[0]["id"]

    return None


async def link_session_to_guest(
    client: Client, property_id: str, session_id: str, guest_id: str
) -> bool:
    response = (
        client.table("chat_sessions")
        .update(
            {
                "guest_id": guest_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", session_id)
        .eq("property_id", property_id)
        .execute()
    )
    return bool(response.data)
