from __future__ import annotations

from supabase import Client

from app.crud.currency import (
    DEFAULT_CURRENCY_CODE,
    get_currency_display_map,
    normalize_currency_code,
    resolve_currency_display,
)


async def _resolve_booking_currency_code(client: Client, data: dict) -> str:
    provided_code = data.get("currency_code")
    if provided_code:
        return normalize_currency_code(str(provided_code))

    room_id = data.get("room_id")
    if not room_id:
        return DEFAULT_CURRENCY_CODE

    query = client.table("rooms").select("currency_code").eq("id", room_id)
    property_id = data.get("property_id")
    if property_id:
        query = query.eq("property_id", property_id)
    room_response = query.limit(1).execute()
    if not room_response.data:
        return DEFAULT_CURRENCY_CODE
    return normalize_currency_code(room_response.data[0].get("currency_code"))


async def _attach_currency_fields(client: Client, rows: list[dict]) -> None:
    currency_display_map = await get_currency_display_map(
        client, [row.get("currency_code") for row in rows]
    )
    for row in rows:
        currency_code = normalize_currency_code(row.get("currency_code"))
        row["currency_code"] = currency_code
        row["currency_display"] = resolve_currency_display(
            currency_code, currency_display_map
        )


async def get_bookings_by_property(
    client: Client, property_id: str, status: str | None = None
) -> list[dict]:
    query = (
        client.table("bookings")
        .select("*, guests(name)")
        .eq("property_id", property_id)
        .order("check_in")
    )
    if status:
        query = query.eq("status", status)
    response = query.execute()
    results = []
    for row in response.data or []:
        guest = row.pop("guests", None)
        row["guest_name"] = guest["name"] if guest else None
        results.append(row)
    await _attach_currency_fields(client, results)
    return results


async def get_bookings_by_room(client: Client, room_id: str) -> list[dict]:
    response = (
        client.table("bookings")
        .select("*, guests(name)")
        .eq("room_id", room_id)
        .order("check_in")
        .execute()
    )
    results = []
    for row in response.data or []:
        guest = row.pop("guests", None)
        row["guest_name"] = guest["name"] if guest else None
        results.append(row)
    await _attach_currency_fields(client, results)
    return results


async def get_booking_by_id(client: Client, booking_id: str) -> dict | None:
    response = (
        client.table("bookings")
        .select("*, guests(name)")
        .eq("id", booking_id)
        .execute()
    )
    if not response.data:
        return None
    row = response.data[0]
    guest = row.pop("guests", None)
    row["guest_name"] = guest["name"] if guest else None
    await _attach_currency_fields(client, [row])
    return row


async def create_booking(client: Client, data: dict) -> dict:
    booking_currency_code = await _resolve_booking_currency_code(client, data)
    insert_data = {**data, "currency_code": booking_currency_code}
    response = client.table("bookings").insert(insert_data).execute()
    booking = response.data[0]
    booking["guest_name"] = None
    await _attach_currency_fields(client, [booking])
    return booking


async def update_booking(client: Client, booking_id: str, data: dict) -> dict | None:
    filtered = {k: v for k, v in data.items() if v is not None}
    if filtered:
        client.table("bookings").update(filtered).eq("id", booking_id).execute()
    return await get_booking_by_id(client, booking_id)


async def get_or_create_guest(
    client: Client, property_id: str, name: str, email: str | None = None, phone: str | None = None
) -> str:
    """Get existing guest by name+property or create new. Returns guest id."""
    query = (
        client.table("guests")
        .select("id")
        .eq("property_id", property_id)
        .eq("name", name)
    )
    if email:
        query = query.eq("email", email)
    existing = query.limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]

    guest_data = {"property_id": property_id, "name": name}
    if email:
        guest_data["email"] = email
    if phone:
        guest_data["phone"] = phone
    response = client.table("guests").insert(guest_data).execute()
    return response.data[0]["id"]
