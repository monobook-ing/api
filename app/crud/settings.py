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


def _resolve_date_window(
    range_preset: str,
    today: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[date, date]:
    if range_preset == "custom":
        if not start_date or not end_date:
            raise ValueError("Custom range requires start_date and end_date")
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")
        return start_date, end_date

    days_by_range = {
        "week": 7,
        "month": 30,
        "year": 365,
    }
    if range_preset not in days_by_range:
        raise ValueError(f"Unsupported dashboard range preset: {range_preset}")
    days = days_by_range[range_preset]
    reference = today or _utc_today()
    return reference - timedelta(days=days - 1), reference


async def get_dashboard_metrics(
    client: Client,
    property_id: str,
    range_preset: str = "year",
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    window_start, window_end = _resolve_date_window(
        range_preset, start_date=start_date, end_date=end_date
    )
    response = (
        client.table("dashboard_metrics")
        .select("*")
        .eq("property_id", property_id)
        .gte("date", window_start.isoformat())
        .lte("date", window_end.isoformat())
        .order("date", desc=True)
        .execute()
    )
    return list(reversed(response.data or []))
