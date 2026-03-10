from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _range_start_date(range_preset: str, today: date | None = None) -> date:
    days_by_range = {
        "month": 30,
        "quarter": 90,
        "year": 365,
    }
    if range_preset not in days_by_range:
        raise ValueError(f"Unsupported dashboard range preset: {range_preset}")
    days = days_by_range[range_preset]
    reference = today or _utc_today()
    return reference - timedelta(days=days - 1)


async def get_dashboard_metrics(
    client: Client, property_id: str, range_preset: str = "year"
) -> list[dict]:
    start_date = _range_start_date(range_preset)
    response = (
        client.table("dashboard_metrics")
        .select("*")
        .eq("property_id", property_id)
        .gte("date", start_date.isoformat())
        .order("date", desc=True)
        .execute()
    )
    return list(reversed(response.data or []))
