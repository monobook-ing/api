"""Agent tool definitions for OpenAI Agents SDK.

Each tool function operates within a property context and reuses existing CRUD functions.
Tool calls are automatically logged to the audit_log table.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from supabase import Client

from app.agents.guardrails import validate_dates, validate_guests
from app.crud.booking import create_booking, get_booking_by_id, get_or_create_guest
from app.crud.property import get_property_by_id
from app.services.embedding import search_similar

logger = logging.getLogger(__name__)


async def log_tool_call(
    client: Client,
    property_id: str,
    session_id: str | None,
    tool_name: str,
    description: str,
    status: str,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
) -> None:
    """Log a tool call to the audit_log table."""
    try:
        client.table("audit_log").insert(
            {
                "property_id": property_id,
                "conversation_id": session_id,
                "source": "widget",
                "tool_name": tool_name,
                "description": description,
                "status": status,
                "request_payload": request_payload,
                "response_payload": response_payload,
            }
        ).execute()
    except Exception as e:
        logger.warning(f"Failed to log tool call: {e}")


# -- Hotel Search Agent Tools --


async def search_rooms(
    client: Client,
    property_id: str,
    api_key: str,
    query: str,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Search for rooms using semantic search + availability filtering."""
    # Semantic search
    results = await search_similar(
        client, property_id, query, api_key, limit=10, threshold=0.5
    )

    # Filter to room-type results
    room_ids = [r["source_id"] for r in results if r["source_type"] == "room"]

    if not room_ids:
        # Fallback: get all active rooms
        all_rooms = (
            client.table("rooms")
            .select("id")
            .eq("property_id", property_id)
            .eq("status", "active")
            .execute()
        )
        room_ids = [r["id"] for r in all_rooms.data or []]

    if not room_ids:
        return {"rooms": [], "message": "No rooms found for this property."}

    # Fetch full room data
    rooms_response = (
        client.table("rooms")
        .select("*")
        .in_("id", room_ids)
        .eq("status", "active")
        .execute()
    )
    rooms = rooms_response.data or []

    # Filter by guest capacity
    if guests:
        rooms = [r for r in rooms if r.get("max_guests", 2) >= guests]

    # Filter by availability
    if check_in and check_out:
        available_rooms = []
        for room in rooms:
            conflicts = (
                client.table("bookings")
                .select("id")
                .eq("room_id", room["id"])
                .neq("status", "cancelled")
                .lt("check_in", check_out)
                .gt("check_out", check_in)
                .execute()
            )
            if not conflicts.data:
                available_rooms.append(room)
        rooms = available_rooms

    await log_tool_call(
        client, property_id, session_id, "search_rooms",
        f"Searched rooms: '{query}'", "success",
        {"query": query, "check_in": check_in, "check_out": check_out, "guests": guests},
        {"count": len(rooms)},
    )

    return {
        "rooms": [
            {
                "id": r["id"],
                "name": r["name"],
                "type": r["type"],
                "description": r.get("description", ""),
                "price_per_night": str(r["price_per_night"]),
                "max_guests": r["max_guests"],
                "amenities": r.get("amenities", []),
                "images": r.get("images", []),
            }
            for r in rooms
        ],
        "count": len(rooms),
    }


async def get_property_info(
    client: Client,
    property_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Get full property information."""
    prop = await get_property_by_id(client, property_id)
    if not prop:
        return {"error": "Property not found"}

    # Get host profile
    host = (
        client.table("host_profiles")
        .select("*")
        .eq("property_id", property_id)
        .execute()
    )
    host_data = host.data[0] if host.data else None

    await log_tool_call(
        client, property_id, session_id, "get_property_info",
        "Retrieved property information", "success",
    )

    result = {
        "name": prop.get("name", ""),
        "description": prop.get("description", ""),
        "city": prop.get("city", ""),
        "country": prop.get("country", ""),
        "rating": str(prop.get("rating", 0)),
    }
    if host_data:
        result["host"] = {
            "name": host_data.get("name", ""),
            "bio": host_data.get("bio", ""),
            "superhost": host_data.get("superhost", False),
            "rating": str(host_data.get("rating", 0)),
        }
    return result


async def get_room_details(
    client: Client,
    property_id: str,
    room_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Get detailed room information including pricing tiers."""
    room = (
        client.table("rooms")
        .select("*")
        .eq("id", room_id)
        .eq("property_id", property_id)
        .single()
        .execute()
    )
    if not room.data:
        return {"error": "Room not found"}

    r = room.data

    # Get pricing tiers
    tiers = (
        client.table("room_guest_tiers")
        .select("*")
        .eq("room_id", room_id)
        .order("min_guests")
        .execute()
    )

    await log_tool_call(
        client, property_id, session_id, "get_room_details",
        f"Retrieved details for room {r['name']}", "success",
    )

    return {
        "id": r["id"],
        "name": r["name"],
        "type": r["type"],
        "description": r.get("description", ""),
        "price_per_night": str(r["price_per_night"]),
        "max_guests": r["max_guests"],
        "bed_config": r.get("bed_config", ""),
        "amenities": r.get("amenities", []),
        "images": r.get("images", []),
        "pricing_tiers": [
            {
                "min_guests": t["min_guests"],
                "max_guests": t["max_guests"],
                "price_per_night": str(t["price_per_night"]),
            }
            for t in tiers.data or []
        ],
    }


async def search_knowledge_base(
    client: Client,
    property_id: str,
    api_key: str,
    query: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Semantic search over knowledge file chunks (hotel policies, FAQ, etc.)."""
    results = await search_similar(
        client, property_id, query, api_key, limit=5, threshold=0.6
    )

    # Filter to knowledge chunks only
    knowledge_results = [r for r in results if r["source_type"] == "knowledge_chunk"]

    await log_tool_call(
        client, property_id, session_id, "search_knowledge_base",
        f"Searched knowledge base: '{query}'", "success",
        {"query": query},
        {"count": len(knowledge_results)},
    )

    return {
        "results": [
            {
                "content": r["content"],
                "file_name": r.get("metadata", {}).get("file_name", ""),
                "similarity": round(r["similarity"], 3),
            }
            for r in knowledge_results
        ],
        "count": len(knowledge_results),
    }


# -- Booking Agent Tools --


async def check_availability(
    client: Client,
    property_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Check if a room is available for the given dates."""
    error = validate_dates(check_in, check_out)
    if error:
        return {"available": False, "error": error}

    conflicts = (
        client.table("bookings")
        .select("id, check_in, check_out, status")
        .eq("room_id", room_id)
        .neq("status", "cancelled")
        .lt("check_in", check_out)
        .gt("check_out", check_in)
        .execute()
    )

    available = not bool(conflicts.data)

    await log_tool_call(
        client, property_id, session_id, "check_availability",
        f"Checked availability for room {room_id}: {'available' if available else 'unavailable'}",
        "success",
        {"room_id": room_id, "check_in": check_in, "check_out": check_out},
        {"available": available},
    )

    return {
        "available": available,
        "room_id": room_id,
        "check_in": check_in,
        "check_out": check_out,
        "conflicts": len(conflicts.data or []),
    }


async def calculate_price(
    client: Client,
    property_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
    guests: int = 2,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Calculate total price for a room booking, considering date overrides and guest tiers."""
    error = validate_dates(check_in, check_out)
    if error:
        return {"error": error}

    guest_error = validate_guests(guests)
    if guest_error:
        return {"error": guest_error}

    # Get base room price
    room = (
        client.table("rooms")
        .select("price_per_night, max_guests, name")
        .eq("id", room_id)
        .single()
        .execute()
    )
    if not room.data:
        return {"error": "Room not found"}

    base_price = float(room.data["price_per_night"])

    # Check guest tier pricing
    tiers = (
        client.table("room_guest_tiers")
        .select("*")
        .eq("room_id", room_id)
        .execute()
    )
    tier_price = None
    for t in tiers.data or []:
        if t["min_guests"] <= guests <= t["max_guests"]:
            tier_price = float(t["price_per_night"])
            break

    nightly_price = tier_price if tier_price is not None else base_price

    # Check date-specific pricing
    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    nights = (co - ci).days

    date_overrides = (
        client.table("room_date_pricing")
        .select("date, price")
        .eq("room_id", room_id)
        .gte("date", check_in)
        .lt("date", check_out)
        .execute()
    )
    override_map = {r["date"]: float(r["price"]) for r in date_overrides.data or []}

    total = 0.0
    current = ci
    for _ in range(nights):
        day_str = current.isoformat()
        total += override_map.get(day_str, nightly_price)
        current = date.fromisoformat(day_str)
        current = date(current.year, current.month, current.day + 1) if current.day < 28 else date.fromisoformat(
            (ci + __import__("datetime").timedelta(days=_ + 1)).isoformat()
        )

    # Simpler approach: just calculate day by day
    from datetime import timedelta
    total = 0.0
    for i in range(nights):
        day = ci + timedelta(days=i)
        day_str = day.isoformat()
        total += override_map.get(day_str, nightly_price)

    taxes = round(total * 0.12, 2)
    service_fee = round(total * 0.04, 2)

    await log_tool_call(
        client, property_id, session_id, "calculate_price",
        f"Calculated price for {room.data['name']}: ${total + taxes + service_fee:.2f}",
        "success",
    )

    return {
        "room_id": room_id,
        "room_name": room.data["name"],
        "nights": nights,
        "nightly_rate": nightly_price,
        "subtotal": total,
        "taxes": taxes,
        "service_fee": service_fee,
        "total": round(total + taxes + service_fee, 2),
        "currency": "USD",
    }


async def tool_create_booking(
    client: Client,
    property_id: str,
    room_id: str,
    guest_name: str,
    guest_email: str | None,
    check_in: str,
    check_out: str,
    guests: int = 2,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Create a booking for a guest."""
    # Validate
    date_error = validate_dates(check_in, check_out)
    if date_error:
        return {"error": date_error}
    guest_error = validate_guests(guests)
    if guest_error:
        return {"error": guest_error}

    # Check availability first
    avail = await check_availability(client, property_id, room_id, check_in, check_out)
    if not avail.get("available"):
        return {"error": "Room is not available for the selected dates."}

    # Calculate price
    pricing = await calculate_price(client, property_id, room_id, check_in, check_out, guests)
    if "error" in pricing:
        return pricing

    # Get or create guest
    guest_id = await get_or_create_guest(client, property_id, guest_name, guest_email)

    # Create booking
    booking_data = {
        "property_id": property_id,
        "room_id": room_id,
        "guest_id": guest_id,
        "check_in": check_in,
        "check_out": check_out,
        "total_price": pricing["total"],
        "status": "ai_pending",
        "ai_handled": True,
        "source": "widget",
        "conversation_id": session_id,
    }

    booking = await create_booking(client, booking_data)

    await log_tool_call(
        client, property_id, session_id, "create_booking",
        f"Created booking for {guest_name}", "success",
        {"room_id": room_id, "check_in": check_in, "check_out": check_out},
        {"booking_id": booking["id"], "total": pricing["total"]},
    )

    return {
        "booking_id": booking["id"],
        "status": "ai_pending",
        "guest_name": guest_name,
        "room_id": room_id,
        "check_in": check_in,
        "check_out": check_out,
        "nights": pricing["nights"],
        "total": pricing["total"],
        "currency": "USD",
        "message": f"Booking created successfully! Confirmation ID: {booking['id'][:8].upper()}",
    }


async def tool_get_booking_status(
    client: Client,
    property_id: str,
    booking_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Get the status of an existing booking."""
    booking = await get_booking_by_id(client, booking_id)
    if not booking:
        return {"error": "Booking not found."}
    if booking.get("property_id") != property_id:
        return {"error": "Booking not found for this property."}

    await log_tool_call(
        client, property_id, session_id, "get_booking_status",
        f"Retrieved booking status: {booking['status']}", "success",
    )

    return {
        "booking_id": booking["id"],
        "status": booking["status"],
        "guest_name": booking.get("guest_name", ""),
        "check_in": booking["check_in"],
        "check_out": booking["check_out"],
        "total_price": str(booking["total_price"]),
    }
