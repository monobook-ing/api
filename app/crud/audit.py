from __future__ import annotations

import base64
import json

from supabase import Client


async def get_audit_log(
    client: Client,
    property_id: str,
    source: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[dict], str | None]:
    query = (
        client.table("audit_log")
        .select("*")
        .eq("property_id", property_id)
        .order("created_at", desc=True)
    )
    if source:
        query = query.eq("source", source)
    if cursor:
        decoded = json.loads(base64.b64decode(cursor))
        query = query.lt("created_at", decoded["created_at"])

    response = query.limit(limit + 1).execute()
    rows = response.data or []

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = base64.b64encode(
            json.dumps({"created_at": last["created_at"], "id": last["id"]}).encode()
        ).decode()

    return rows, next_cursor


async def create_audit_entry(client: Client, data: dict) -> dict:
    response = client.table("audit_log").insert(data).execute()
    return response.data[0]
