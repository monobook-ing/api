from __future__ import annotations

from supabase import Client


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
    return row


async def create_booking(client: Client, data: dict) -> dict:
    response = client.table("bookings").insert(data).execute()
    booking = response.data[0]
    booking["guest_name"] = None
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
