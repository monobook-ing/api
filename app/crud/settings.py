from __future__ import annotations

from supabase import Client


async def get_connections(client: Client, property_id: str, table: str) -> list[dict]:
    response = (
        client.table(table)
        .select("*")
        .eq("property_id", property_id)
        .execute()
    )
    return response.data or []


async def upsert_connection(
    client: Client, property_id: str, table: str, provider: str, enabled: bool
) -> dict:
    existing = (
        client.table(table)
        .select("*")
        .eq("property_id", property_id)
        .eq("provider", provider)
        .execute()
    )
    if existing.data:
        response = (
            client.table(table)
            .update({"enabled": enabled})
            .eq("property_id", property_id)
            .eq("provider", provider)
            .execute()
        )
        return response.data[0]
    else:
        response = (
            client.table(table)
            .insert({"property_id": property_id, "provider": provider, "enabled": enabled})
            .execute()
        )
        return response.data[0]


async def get_dashboard_metrics(client: Client, property_id: str, limit: int = 12) -> list[dict]:
    response = (
        client.table("dashboard_metrics")
        .select("*")
        .eq("property_id", property_id)
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(response.data or []))
