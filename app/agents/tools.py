"""Agent tool definitions for OpenAI Agents SDK.

Each tool function operates within a property context and reuses existing CRUD functions.
Tool calls are automatically logged to the audit_log table.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from typing import Any

from supabase import Client

from app.agents.guardrails import validate_dates, validate_guests
from app.crud.booking import create_booking, get_booking_by_id, get_or_create_guest
from app.crud.chat import link_session_to_guest
from app.crud.property import get_property_by_id
from app.services.embedding import search_similar

logger = logging.getLogger(__name__)

PET_FRIENDLY_KEYWORDS = (
    "pet friendly",
    "pets allowed",
    "pets welcome",
    "pet-friendly",
)
TAX_RATE = 0.12
SERVICE_FEE_RATE = 0.04


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _contains_ci(value: Any, term: str) -> bool:
    if value is None:
        return False
    return term in str(value).lower()


def _property_name_from_row(row: dict[str, Any]) -> str:
    account = row.get("accounts")
    if isinstance(account, list):
        account = account[0] if account else {}
    if isinstance(account, dict):
        return str(account.get("name", "")).strip()
    return ""


def _room_is_pet_friendly(amenities: list[str] | None) -> bool:
    if not amenities:
        return False
    normalized = [str(amenity).lower() for amenity in amenities]
    return any(
        any(keyword in amenity for keyword in PET_FRIENDLY_KEYWORDS)
        for amenity in normalized
    )


def _haversine_distance_km(
    origin_lat: float,
    origin_lng: float,
    target_lat: float,
    target_lng: float,
) -> float:
    earth_radius_km = 6371.0
    d_lat = math.radians(target_lat - origin_lat)
    d_lng = math.radians(target_lng - origin_lng)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(origin_lat))
        * math.cos(math.radians(target_lat))
        * math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


async def _filter_available_rooms(
    client: Client,
    rooms: list[dict[str, Any]],
    check_in: str,
    check_out: str,
) -> list[dict[str, Any]]:
    if not rooms:
        return []

    room_ids = [room["id"] for room in rooms]
    conflicts = (
        client.table("bookings")
        .select("room_id")
        .in_("room_id", room_ids)
        .neq("status", "cancelled")
        .lt("check_in", check_out)
        .gt("check_out", check_in)
        .execute()
    )
    conflict_room_ids = {entry["room_id"] for entry in conflicts.data or []}
    return [room for room in rooms if room["id"] not in conflict_room_ids]


def _nightly_rate_for_guests(
    room: dict[str, Any],
    guests: int | None,
    guest_tiers: list[dict[str, Any]],
) -> float:
    base_rate = _to_float(room.get("price_per_night"))
    if guests is None:
        return base_rate

    for tier in guest_tiers:
        min_guests = int(tier.get("min_guests", 1))
        max_guests = int(tier.get("max_guests", 1))
        if min_guests <= guests <= max_guests:
            return _to_float(tier.get("price_per_night"))
    return base_rate


def _calculate_room_total_price(
    room: dict[str, Any],
    guests: int | None,
    check_in: str,
    check_out: str,
    guest_tiers: list[dict[str, Any]],
    date_overrides: list[dict[str, Any]],
) -> float:
    check_in_date = date.fromisoformat(check_in)
    check_out_date = date.fromisoformat(check_out)
    nights = (check_out_date - check_in_date).days
    nightly_rate = _nightly_rate_for_guests(room, guests, guest_tiers)

    override_map = {
        str(override["date"]): _to_float(override["price"])
        for override in date_overrides
    }

    subtotal = 0.0
    for i in range(nights):
        current_day = check_in_date + timedelta(days=i)
        current_key = current_day.isoformat()
        subtotal += override_map.get(current_key, nightly_rate)

    taxes = round(subtotal * TAX_RATE, 2)
    service_fee = round(subtotal * SERVICE_FEE_RATE, 2)
    return round(subtotal + taxes + service_fee, 2)


def _empty_hotel_search_result(
    applied_filters: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return {
        "hotels": [],
        "count_hotels": 0,
        "count_rooms": 0,
        "applied_filters": applied_filters,
        "message": message,
    }


async def log_tool_call(
    client: Client,
    property_id: str,
    session_id: str | None,
    tool_name: str,
    description: str,
    status: str,
    source: str = "widget",
    request_payload: dict | None = None,
    response_payload: dict | None = None,
) -> None:
    """Log a tool call to the audit_log table."""
    try:
        client.table("audit_log").insert(
            {
                "property_id": property_id,
                "conversation_id": session_id,
                "source": source,
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
    source: str = "widget",
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

    # Fetch property name for display
    prop = await get_property_by_id(client, property_id)
    property_name = prop.get("name", "") if prop else ""

    await log_tool_call(
        client, property_id, session_id, "search_rooms",
        f"Searched rooms: '{query}'", "success",
        source,
        {"query": query, "check_in": check_in, "check_out": check_out, "guests": guests},
        {"count": len(rooms)},
    )

    return {
        "property_id": property_id,
        "property_name": property_name,
        "rooms": [
            {
                "id": r["id"],
                "property_id": r["property_id"],
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


async def search_hotels(
    client: Client,
    query: str = "",
    property_name: str | None = None,
    city: str | None = None,
    country: str | None = None,
    room_name: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = 20.0,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int | None = None,
    pet_friendly: bool | None = None,
    budget_per_night_max: float | None = None,
    budget_total_max: float | None = None,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    normalized_query = (query or "").strip().lower()
    normalized_property_name = (property_name or "").strip().lower()
    normalized_city = (city or "").strip().lower()
    normalized_country = (country or "").strip().lower()
    normalized_room_name = (room_name or "").strip().lower()

    has_coordinate_pair = lat is not None and lng is not None
    if (lat is None) != (lng is None):
        return {"error": "Both lat and lng must be provided together."}
    if radius_km <= 0:
        return {"error": "radius_km must be greater than 0."}

    has_primary_criteria = any(
        (
            normalized_query,
            normalized_property_name,
            normalized_city,
            normalized_country,
            normalized_room_name,
            has_coordinate_pair,
        )
    )
    if not has_primary_criteria:
        return {
            "error": (
                "At least one search criterion is required: query, property_name, city, "
                "country, room_name, or lat/lng."
            )
        }

    if (check_in and not check_out) or (check_out and not check_in):
        return {"error": "Both check_in and check_out must be provided together."}

    if check_in and check_out:
        date_error = validate_dates(check_in, check_out)
        if date_error:
            return {"error": date_error}

    if guests is not None:
        guest_error = validate_guests(guests)
        if guest_error:
            return {"error": guest_error}

    if budget_per_night_max is not None and budget_per_night_max <= 0:
        return {"error": "budget_per_night_max must be greater than 0."}

    if budget_total_max is not None and budget_total_max <= 0:
        return {"error": "budget_total_max must be greater than 0."}

    if budget_total_max is not None and not (check_in and check_out):
        return {
            "error": "budget_total_max requires both check_in and check_out dates."
        }

    applied_filters: dict[str, Any] = {}
    if normalized_query:
        applied_filters["query"] = query.strip()
    if normalized_property_name:
        applied_filters["property_name"] = property_name
    if normalized_city:
        applied_filters["city"] = city
    if normalized_country:
        applied_filters["country"] = country
    if normalized_room_name:
        applied_filters["room_name"] = room_name
    if has_coordinate_pair:
        applied_filters["lat"] = lat
        applied_filters["lng"] = lng
        applied_filters["radius_km"] = radius_km
    if check_in and check_out:
        applied_filters["check_in"] = check_in
        applied_filters["check_out"] = check_out
    if guests is not None:
        applied_filters["guests"] = guests
    if pet_friendly is not None:
        applied_filters["pet_friendly"] = pet_friendly
    if budget_per_night_max is not None:
        applied_filters["budget_per_night_max"] = budget_per_night_max
    if budget_total_max is not None:
        applied_filters["budget_total_max"] = budget_total_max

    properties_response = (
        client.table("properties")
        .select("id, city, country, lat, lng, description, accounts!inner(name)")
        .execute()
    )
    properties_raw = properties_response.data or []

    properties: dict[str, dict[str, Any]] = {}
    for row in properties_raw:
        pid = str(row["id"])
        prop_name = _property_name_from_row(row)
        prop_city = row.get("city")
        prop_country = row.get("country")
        prop_description = row.get("description")
        prop_lat = row.get("lat")
        prop_lng = row.get("lng")

        if normalized_property_name and not _contains_ci(prop_name, normalized_property_name):
            continue
        if normalized_city and not _contains_ci(prop_city, normalized_city):
            continue
        if normalized_country and not _contains_ci(prop_country, normalized_country):
            continue

        distance_km: float | None = None
        if has_coordinate_pair:
            if prop_lat is None or prop_lng is None:
                continue
            distance_km = _haversine_distance_km(
                float(lat),
                float(lng),
                float(prop_lat),
                float(prop_lng),
            )
            if distance_km > radius_km:
                continue

        properties[pid] = {
            "property_id": pid,
            "property_name": prop_name,
            "city": prop_city,
            "country": prop_country,
            "lat": prop_lat,
            "lng": prop_lng,
            "description": prop_description,
            "distance_km": round(distance_km, 3) if distance_km is not None else None,
        }

    if not properties:
        return _empty_hotel_search_result(
            applied_filters,
            "No hotels matched the provided filters.",
        )

    rooms_response = (
        client.table("rooms")
        .select(
            "id, property_id, name, type, description, price_per_night, "
            "max_guests, amenities, images"
        )
        .in_("property_id", list(properties.keys()))
        .eq("status", "active")
        .execute()
    )
    rooms = rooms_response.data or []

    if normalized_room_name:
        rooms = [
            room for room in rooms
            if _contains_ci(room.get("name"), normalized_room_name)
            or _contains_ci(room.get("type"), normalized_room_name)
        ]

    if guests is not None:
        rooms = [
            room for room in rooms
            if int(room.get("max_guests", 0)) >= guests
        ]

    if pet_friendly:
        rooms = [
            room for room in rooms
            if _room_is_pet_friendly(room.get("amenities"))
        ]

    if budget_per_night_max is not None:
        rooms = [
            room
            for room in rooms
            if _to_float(room.get("price_per_night")) <= budget_per_night_max
        ]

    if check_in and check_out:
        rooms = await _filter_available_rooms(client, rooms, check_in, check_out)

    room_total_map: dict[str, float] = {}
    if rooms and check_in and check_out and budget_total_max is not None:
        room_ids = [room["id"] for room in rooms]

        guest_tiers_response = (
            client.table("room_guest_tiers")
            .select("room_id, min_guests, max_guests, price_per_night")
            .in_("room_id", room_ids)
            .execute()
        )
        guest_tiers_by_room: dict[str, list[dict[str, Any]]] = {rid: [] for rid in room_ids}
        for tier in guest_tiers_response.data or []:
            room_id = str(tier["room_id"])
            guest_tiers_by_room.setdefault(room_id, []).append(tier)

        date_overrides_response = (
            client.table("room_date_pricing")
            .select("room_id, date, price")
            .in_("room_id", room_ids)
            .gte("date", check_in)
            .lt("date", check_out)
            .execute()
        )
        date_overrides_by_room: dict[str, list[dict[str, Any]]] = {rid: [] for rid in room_ids}
        for override in date_overrides_response.data or []:
            room_id = str(override["room_id"])
            date_overrides_by_room.setdefault(room_id, []).append(override)

        budget_filtered_rooms: list[dict[str, Any]] = []
        for room in rooms:
            total_price = _calculate_room_total_price(
                room,
                guests,
                check_in,
                check_out,
                guest_tiers_by_room.get(str(room["id"]), []),
                date_overrides_by_room.get(str(room["id"]), []),
            )
            room_total_map[str(room["id"])] = total_price
            if total_price <= budget_total_max:
                budget_filtered_rooms.append(room)
        rooms = budget_filtered_rooms

    if normalized_query:
        query_filtered_rooms: list[dict[str, Any]] = []
        for room in rooms:
            pid = str(room["property_id"])
            prop = properties.get(pid)
            if not prop:
                continue

            room_match = any(
                (
                    _contains_ci(room.get("name"), normalized_query),
                    _contains_ci(room.get("type"), normalized_query),
                    _contains_ci(room.get("description"), normalized_query),
                    any(
                        _contains_ci(amenity, normalized_query)
                        for amenity in (room.get("amenities") or [])
                    ),
                )
            )
            property_match = any(
                (
                    _contains_ci(prop.get("property_name"), normalized_query),
                    _contains_ci(prop.get("description"), normalized_query),
                    _contains_ci(prop.get("city"), normalized_query),
                    _contains_ci(prop.get("country"), normalized_query),
                )
            )
            if room_match or property_match:
                query_filtered_rooms.append(room)
        rooms = query_filtered_rooms

    rooms_by_property: dict[str, list[dict[str, Any]]] = {}
    for room in rooms:
        pid = str(room["property_id"])
        if pid not in properties:
            continue
        rooms_by_property.setdefault(pid, []).append(room)

    hotels: list[dict[str, Any]] = []
    for pid, property_rooms in rooms_by_property.items():
        prop = properties[pid]
        sorted_rooms = sorted(
            property_rooms,
            key=lambda item: _to_float(item.get("price_per_night")),
        )
        matching_rooms = []
        for room in sorted_rooms:
            room_entry: dict[str, Any] = {
                "id": room["id"],
                "property_id": room["property_id"],
                "name": room["name"],
                "type": room["type"],
                "description": room.get("description", ""),
                "price_per_night": _to_float(room.get("price_per_night")),
                "max_guests": int(room.get("max_guests", 0)),
                "amenities": room.get("amenities", []),
                "images": room.get("images", []),
            }
            room_id = str(room["id"])
            if room_id in room_total_map:
                room_entry["estimated_total_price"] = room_total_map[room_id]
            matching_rooms.append(room_entry)

        min_price_per_night = min(
            _to_float(room.get("price_per_night")) for room in property_rooms
        )
        hotels.append(
            {
                "property_id": prop["property_id"],
                "property_name": prop["property_name"],
                "city": prop["city"],
                "country": prop["country"],
                "lat": prop["lat"],
                "lng": prop["lng"],
                "distance_km": prop["distance_km"],
                "min_price_per_night": round(min_price_per_night, 2),
                "available_rooms_count": len(matching_rooms),
                "pet_friendly_option": any(
                    _room_is_pet_friendly(room.get("amenities"))
                    for room in property_rooms
                ),
                "matching_rooms": matching_rooms,
            }
        )

    if has_coordinate_pair:
        hotels.sort(
            key=lambda hotel: (
                hotel["distance_km"] if hotel["distance_km"] is not None else float("inf"),
                hotel["property_name"].lower(),
            )
        )
    else:
        hotels.sort(key=lambda hotel: hotel["property_name"].lower())

    count_hotels = len(hotels)
    count_rooms = sum(len(hotel["matching_rooms"]) for hotel in hotels)
    message = (
        f"Found {count_hotels} hotel(s) with {count_rooms} matching room(s)."
        if count_hotels > 0
        else "No hotels matched the provided filters."
    )

    if hotels:
        for hotel in hotels:
            await log_tool_call(
                client=client,
                property_id=hotel["property_id"],
                session_id=session_id,
                tool_name="search_hotels",
                description=f"Cross-property hotel search: '{query or room_name or city or country or property_name or 'filters'}'",
                status="success",
                source=source,
                request_payload=applied_filters,
                response_payload={
                    "count_hotels": count_hotels,
                    "count_rooms": count_rooms,
                },
            )

    return {
        "hotels": hotels,
        "count_hotels": count_hotels,
        "count_rooms": count_rooms,
        "applied_filters": applied_filters,
        "message": message,
    }


async def get_property_info(
    client: Client,
    property_id: str,
    session_id: str | None = None,
    source: str = "widget",
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
        source,
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
    source: str = "widget",
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
        source,
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
    source: str = "widget",
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
        source,
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
    source: str = "widget",
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
        source,
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
    source: str = "widget",
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
        source,
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
    source: str = "widget",
    booking_status: str = "ai_pending",
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
    avail = await check_availability(
        client,
        property_id,
        room_id,
        check_in,
        check_out,
        session_id=session_id,
        source=source,
    )
    if not avail.get("available"):
        return {"error": "Room is not available for the selected dates."}

    # Calculate price
    pricing = await calculate_price(
        client,
        property_id,
        room_id,
        check_in,
        check_out,
        guests,
        session_id=session_id,
        source=source,
    )
    if "error" in pricing:
        return pricing

    # Get or create guest
    guest_id = await get_or_create_guest(client, property_id, guest_name, guest_email)
    if session_id:
        await link_session_to_guest(client, property_id, session_id, guest_id)

    # Create booking
    booking_data = {
        "property_id": property_id,
        "room_id": room_id,
        "guest_id": guest_id,
        "check_in": check_in,
        "check_out": check_out,
        "total_price": pricing["total"],
        "status": booking_status,
        "ai_handled": True,
        "source": source,
        "conversation_id": session_id,
    }

    booking = await create_booking(client, booking_data)

    await log_tool_call(
        client, property_id, session_id, "create_booking",
        f"Created booking for {guest_name}", "success",
        source,
        {"room_id": room_id, "check_in": check_in, "check_out": check_out},
        {"booking_id": booking["id"], "total": pricing["total"]},
    )

    return {
        "booking_id": booking["id"],
        "status": booking_status,
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
    source: str = "widget",
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
        source,
    )

    return {
        "booking_id": booking["id"],
        "status": booking["status"],
        "guest_name": booking.get("guest_name", ""),
        "check_in": booking["check_in"],
        "check_out": booking["check_out"],
        "total_price": str(booking["total_price"]),
    }
