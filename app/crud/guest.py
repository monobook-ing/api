from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_room_name(booking: dict) -> str:
    room_data = booking.get("rooms")
    if isinstance(room_data, dict):
        return str(room_data.get("name") or "Unknown Room")
    if isinstance(room_data, list) and room_data and isinstance(room_data[0], dict):
        return str(room_data[0].get("name") or "Unknown Room")
    return "Unknown Room"


def _map_latest_booking(booking: dict | None) -> dict | None:
    if not booking:
        return None
    return {
        "id": booking["id"],
        "room_id": booking["room_id"],
        "room_name": _extract_room_name(booking),
        "check_in": booking["check_in"],
        "check_out": booking["check_out"],
        "status": booking["status"],
        "total_price": _as_float(booking.get("total_price")),
        "ai_handled": bool(booking.get("ai_handled", False)),
    }


def _build_guest_summary(guest: dict, bookings: list[dict]) -> dict:
    sorted_bookings = sorted(bookings, key=lambda row: row.get("check_in", ""), reverse=True)
    latest_booking = sorted_bookings[0] if sorted_bookings else None
    last_stay_date = None
    if sorted_bookings:
        last_stay_date = max(
            (booking.get("check_out") for booking in sorted_bookings if booking.get("check_out")),
            default=None,
        )

    return {
        "id": guest["id"],
        "property_id": guest["property_id"],
        "name": guest["name"],
        "email": guest.get("email"),
        "phone": guest.get("phone"),
        "notes": guest.get("notes") or "",
        "total_stays": len(sorted_bookings),
        "last_stay_date": last_stay_date,
        "total_spent": sum(_as_float(booking.get("total_price")) for booking in sorted_bookings),
        "latest_booking": _map_latest_booking(latest_booking),
        "created_at": guest["created_at"],
        "updated_at": guest.get("updated_at") or guest["created_at"],
    }


def _map_booking(booking: dict) -> dict:
    return {
        "id": booking["id"],
        "guest_id": booking["guest_id"],
        "room_id": booking["room_id"],
        "room_name": _extract_room_name(booking),
        "property_id": booking["property_id"],
        "check_in": booking["check_in"],
        "check_out": booking["check_out"],
        "status": booking["status"],
        "total_price": _as_float(booking.get("total_price")),
        "ai_handled": bool(booking.get("ai_handled", False)),
        "conversation_id": booking.get("conversation_id"),
    }


def _map_conversation_message(message: dict) -> dict:
    role = "guest" if message.get("role") == "user" else "ai"
    return {
        "role": role,
        "text": message.get("content") or "",
        "timestamp": message.get("created_at"),
    }


def _build_guest_search_filter(search: str) -> str:
    search_term = search.replace(",", "\\,")
    return (
        f"name.ilike.%{search_term}%,"
        f"email.ilike.%{search_term}%,"
        f"phone.ilike.%{search_term}%"
    )


async def get_guest_by_id(client: Client, property_id: str, guest_id: str) -> dict | None:
    response = (
        client.table("guests")
        .select("*")
        .eq("id", guest_id)
        .eq("property_id", property_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0]


async def get_guests_by_property(
    client: Client,
    property_id: str,
    search: str | None = None,
    room_id: str | None = None,
    status: str | None = None,
) -> list[dict]:
    query = client.table("guests").select("*").eq("property_id", property_id)

    if room_id or status:
        filtered_booking_query = (
            client.table("bookings")
            .select("guest_id")
            .eq("property_id", property_id)
        )
        if room_id:
            filtered_booking_query = filtered_booking_query.eq("room_id", room_id)
        if status:
            filtered_booking_query = filtered_booking_query.eq("status", status)

        filtered_bookings = filtered_booking_query.execute().data or []
        filtered_guest_ids = list(
            {
                booking.get("guest_id")
                for booking in filtered_bookings
                if isinstance(booking.get("guest_id"), str)
            }
        )
        if not filtered_guest_ids:
            return []
        query = query.in_("id", filtered_guest_ids)

    if search and search.strip():
        query = query.or_(_build_guest_search_filter(search.strip()))

    guests = query.order("created_at", desc=True).execute().data or []
    if not guests:
        return []

    guest_ids = [guest["id"] for guest in guests]
    booking_rows = (
        client.table("bookings")
        .select(
            "id, guest_id, room_id, property_id, check_in, check_out, status, total_price, ai_handled, "
            "conversation_id, rooms(name)"
        )
        .eq("property_id", property_id)
        .in_("guest_id", guest_ids)
        .order("check_in", desc=True)
        .execute()
        .data
        or []
    )

    bookings_by_guest: dict[str, list[dict]] = {guest_id: [] for guest_id in guest_ids}
    for booking in booking_rows:
        booking_guest_id = booking.get("guest_id")
        if booking_guest_id in bookings_by_guest:
            bookings_by_guest[booking_guest_id].append(booking)

    return [
        _build_guest_summary(guest, bookings_by_guest.get(guest["id"], []))
        for guest in guests
    ]


async def get_guest_detail(client: Client, property_id: str, guest_id: str) -> dict | None:
    guest = await get_guest_by_id(client, property_id, guest_id)
    if not guest:
        return None

    booking_rows = (
        client.table("bookings")
        .select(
            "id, guest_id, room_id, property_id, check_in, check_out, status, total_price, ai_handled, "
            "conversation_id, rooms(name)"
        )
        .eq("property_id", property_id)
        .eq("guest_id", guest_id)
        .order("check_in", desc=True)
        .execute()
        .data
        or []
    )

    session_rows = (
        client.table("chat_sessions")
        .select("id, guest_id, source, created_at")
        .eq("property_id", property_id)
        .eq("guest_id", guest_id)
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )

    session_ids = [session["id"] for session in session_rows]
    messages_by_session: dict[str, list[dict]] = {}
    if session_ids:
        message_rows = (
            client.table("chat_messages")
            .select("session_id, role, content, created_at")
            .in_("session_id", session_ids)
            .order("created_at")
            .execute()
            .data
            or []
        )
        for message in message_rows:
            session_id = message.get("session_id")
            if not isinstance(session_id, str):
                continue
            messages_by_session.setdefault(session_id, []).append(
                _map_conversation_message(message)
            )

    detail = _build_guest_summary(guest, booking_rows)
    detail["bookings"] = [_map_booking(booking) for booking in booking_rows]
    detail["conversations"] = [
        {
            "id": session["id"],
            "guest_id": session.get("guest_id"),
            "channel": session.get("source") or "widget",
            "started_at": session["created_at"],
            "messages": messages_by_session.get(session["id"], []),
        }
        for session in session_rows
    ]
    return detail


async def update_guest(
    client: Client, property_id: str, guest_id: str, data: dict
) -> dict | None:
    if not data:
        return await get_guest_detail(client, property_id, guest_id)

    update_data: dict[str, object] = {}
    if "name" in data and data["name"] is not None:
        update_data["name"] = data["name"]
    if "email" in data:
        update_data["email"] = data["email"]
    if "phone" in data:
        update_data["phone"] = data["phone"]
    if "notes" in data:
        update_data["notes"] = data["notes"] if data["notes"] is not None else ""

    if not update_data:
        return await get_guest_detail(client, property_id, guest_id)

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    response = (
        client.table("guests")
        .update(update_data)
        .eq("id", guest_id)
        .eq("property_id", property_id)
        .execute()
    )
    if not response.data:
        return None

    return await get_guest_detail(client, property_id, guest_id)
