from __future__ import annotations

from supabase import Client

from app.crud.currency import (
    get_currency_display_map,
    normalize_currency_code,
    resolve_currency_display,
)


async def get_rooms_by_property(client: Client, property_id: str) -> list[dict]:
    response = (
        client.table("rooms")
        .select("*")
        .eq("property_id", property_id)
        .order("created_at")
        .execute()
    )
    rooms = response.data or []
    currency_display_map = await get_currency_display_map(
        client, [room.get("currency_code") for room in rooms]
    )
    for room in rooms:
        currency_code = normalize_currency_code(room.get("currency_code"))
        room["currency_code"] = currency_code
        room["currency_display"] = resolve_currency_display(
            currency_code, currency_display_map
        )
        room["guest_tiers"] = await _get_guest_tiers(client, room["id"])
        room["date_overrides"] = await _get_date_overrides(client, room["id"])
    return rooms


async def get_room_by_id(client: Client, room_id: str) -> dict | None:
    response = client.table("rooms").select("*").eq("id", room_id).execute()
    if not response.data:
        return None
    room = response.data[0]
    currency_code = normalize_currency_code(room.get("currency_code"))
    room["currency_code"] = currency_code
    currency_display_map = await get_currency_display_map(client, [currency_code])
    room["currency_display"] = resolve_currency_display(
        currency_code, currency_display_map
    )
    room["guest_tiers"] = await _get_guest_tiers(client, room_id)
    room["date_overrides"] = await _get_date_overrides(client, room_id)
    return room


async def create_room(client: Client, property_id: str, data: dict) -> dict:
    row = {
        **data,
        "property_id": property_id,
        "currency_code": normalize_currency_code(data.get("currency_code")),
    }
    response = client.table("rooms").insert(row).execute()
    room = response.data[0] if response.data else None
    if not room:
        return {}
    return await get_room_by_id(client, room["id"]) or {}


async def update_room(client: Client, room_id: str, data: dict) -> dict | None:
    filtered = {k: v for k, v in data.items() if v is not None}
    if "currency_code" in filtered:
        filtered["currency_code"] = normalize_currency_code(filtered.get("currency_code"))
    if filtered:
        client.table("rooms").update(filtered).eq("id", room_id).execute()
    return await get_room_by_id(client, room_id)


async def delete_room(client: Client, room_id: str) -> bool:
    response = client.table("rooms").delete().eq("id", room_id).execute()
    return bool(response.data)


async def upsert_room_pricing(
    client: Client, room_id: str, date_overrides: list[dict], guest_tiers: list[dict]
) -> None:
    # Replace date overrides
    client.table("room_date_pricing").delete().eq("room_id", room_id).execute()
    if date_overrides:
        rows = [{"room_id": room_id, "date": d["date"], "price": d["price"]} for d in date_overrides]
        client.table("room_date_pricing").insert(rows).execute()

    # Replace guest tiers
    client.table("room_guest_tiers").delete().eq("room_id", room_id).execute()
    if guest_tiers:
        rows = [
            {
                "room_id": room_id,
                "min_guests": t["min_guests"],
                "max_guests": t["max_guests"],
                "price_per_night": t["price_per_night"],
            }
            for t in guest_tiers
        ]
        client.table("room_guest_tiers").insert(rows).execute()


async def _get_guest_tiers(client: Client, room_id: str) -> list[dict]:
    resp = (
        client.table("room_guest_tiers")
        .select("*")
        .eq("room_id", room_id)
        .order("min_guests")
        .execute()
    )
    return resp.data or []


async def _get_date_overrides(client: Client, room_id: str) -> list[dict]:
    resp = (
        client.table("room_date_pricing")
        .select("*")
        .eq("room_id", room_id)
        .order("date")
        .execute()
    )
    return resp.data or []
