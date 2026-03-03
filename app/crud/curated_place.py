from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client


def _normalize_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


async def list_curated_places(
    client: Client,
    property_id: str,
    meal_type: str | None = None,
    tags: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    query = (
        client.table("curated_places")
        .select("*")
        .eq("property_id", property_id)
        .is_("deleted_at", "null")
        .order("sponsored", desc=True)
        .order("sort_order")
        .order("created_at")
    )

    if meal_type and meal_type.strip():
        query = query.contains("meal_types", [meal_type.strip()])

    normalized_tags = _normalize_terms(tags)
    if normalized_tags:
        query = query.contains("tags", normalized_tags)

    if isinstance(limit, int) and limit > 0:
        query = query.limit(limit)

    response = query.execute()
    return response.data or []


async def get_curated_place(
    client: Client,
    property_id: str,
    place_id: str,
) -> dict | None:
    response = (
        client.table("curated_places")
        .select("*")
        .eq("property_id", property_id)
        .eq("id", place_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0]


async def create_curated_place(
    client: Client,
    property_id: str,
    data: dict,
) -> dict:
    row = {
        **data,
        "property_id": property_id,
    }
    response = client.table("curated_places").insert(row).execute()
    if not response.data:
        return {}
    return response.data[0]


async def update_curated_place(
    client: Client,
    property_id: str,
    place_id: str,
    data: dict,
) -> dict | None:
    filtered = {k: v for k, v in data.items() if v is not None}
    if filtered:
        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
        client.table("curated_places").update(filtered).eq("id", place_id).eq(
            "property_id", property_id
        ).is_("deleted_at", "null").execute()
    return await get_curated_place(client, property_id, place_id)


async def delete_curated_place(
    client: Client,
    property_id: str,
    place_id: str,
    user_id: str,
) -> bool:
    response = (
        client.table("curated_places")
        .update(
            {
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": user_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", place_id)
        .eq("property_id", property_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return bool(response.data)
