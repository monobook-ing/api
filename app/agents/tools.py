"""Agent tool definitions for OpenAI Agents SDK.

Each tool function operates within a property context and reuses existing CRUD functions.
Tool calls are automatically logged to the audit_log table.
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid as _uuid
from datetime import date, datetime, timedelta
from typing import Any

from supabase import Client

from app.agents.guardrails import validate_dates, validate_guests
from app.crud.booking import create_booking, get_booking_by_id, get_or_create_guest
from app.crud.chat import link_session_to_guest
from app.crud.curated_place import list_curated_places
from app.crud.currency import (
    get_currency_display_map,
    normalize_currency_code,
    resolve_currency_display,
)
from app.crud.property import get_property_by_id
from app.crud.service import get_account_id_for_property, get_service_by_id, list_services
from app.core.config import get_settings
from app.services.places import PlacesService
from app.services.booking_notifications import (
    notify_booking_success,
    notify_service_booking_success,
)
from app.services.embedding import search_similar
from app.services.resend import send_service_booking_email

logger = logging.getLogger(__name__)
settings = get_settings()

PET_FRIENDLY_KEYWORDS = (
    "pet friendly",
    "pets allowed",
    "pets welcome",
    "pet-friendly",
)
TAX_RATE = 0.12
SERVICE_FEE_RATE = 0.04
_CURRENCY_ALPHA_PATTERN = re.compile(r"[A-Za-z]")


def _is_valid_uuid(value: str | None) -> bool:
    """Check if a string is a valid UUID (v1-v5)."""
    if not value:
        return False
    try:
        _uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _contains_ci(value: Any, term: str) -> bool:
    if value is None:
        return False
    return term in str(value).lower()


def _is_symbol_currency_display(currency_display: str) -> bool:
    return _CURRENCY_ALPHA_PATTERN.search(currency_display) is None


def _format_price_for_log(amount: float, currency_display: str) -> str:
    formatted = f"{amount:.2f}"
    if _is_symbol_currency_display(currency_display):
        return f"{currency_display}{formatted}"
    return f"{formatted} {currency_display}"


def _property_name_from_row(row: dict[str, Any]) -> str:
    return str(row.get("name", "")).strip()


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
    currency_display_map = await get_currency_display_map(
        client, [room.get("currency_code") for room in rooms]
    )

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
                "currency_code": normalize_currency_code(r.get("currency_code")),
                "currency_display": resolve_currency_display(
                    normalize_currency_code(r.get("currency_code")),
                    currency_display_map,
                ),
                "max_guests": r["max_guests"],
                "amenities": r.get("amenities", []),
                "images": r.get("images", []),
            }
            for r in rooms
        ],
        "count": len(rooms),
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
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
        .select("id, name, city, country, lat, lng, description")
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
            "currency_code, max_guests, amenities, images"
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

    currency_display_map = await get_currency_display_map(
        client, [room.get("currency_code") for room in rooms]
    )

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
            room_currency_code = normalize_currency_code(room.get("currency_code"))
            room_currency_display = resolve_currency_display(
                room_currency_code, currency_display_map
            )
            room_entry: dict[str, Any] = {
                "id": room["id"],
                "property_id": room["property_id"],
                "name": room["name"],
                "type": room["type"],
                "description": room.get("description", ""),
                "price_per_night": _to_float(room.get("price_per_night")),
                "currency_code": room_currency_code,
                "currency_display": room_currency_display,
                "max_guests": int(room.get("max_guests", 0)),
                "amenities": room.get("amenities", []),
                "images": room.get("images", []),
            }
            room_id = str(room["id"])
            if room_id in room_total_map:
                room_entry["estimated_total_price"] = room_total_map[room_id]
                room_entry["estimated_total_price_currency_code"] = room_currency_code
                room_entry["estimated_total_price_currency_display"] = room_currency_display
            matching_rooms.append(room_entry)

        min_price_per_night = min(
            _to_float(room.get("price_per_night")) for room in property_rooms
        )
        min_price_currency_code = normalize_currency_code(
            property_rooms[0].get("currency_code")
        )
        min_price_currency_display = resolve_currency_display(
            min_price_currency_code, currency_display_map
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
                "min_price_currency_code": min_price_currency_code,
                "min_price_currency_display": min_price_currency_display,
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
    currency_code = normalize_currency_code(r.get("currency_code"))
    currency_display_map = await get_currency_display_map(client, [currency_code])
    currency_display = resolve_currency_display(currency_code, currency_display_map)

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
        "currency_code": currency_code,
        "currency_display": currency_display,
        "max_guests": r["max_guests"],
        "bed_config": r.get("bed_config", ""),
        "amenities": r.get("amenities", []),
        "images": r.get("images", []),
        "pricing_tiers": [
            {
                "min_guests": t["min_guests"],
                "max_guests": t["max_guests"],
                "price_per_night": str(t["price_per_night"]),
                "currency_code": currency_code,
                "currency_display": currency_display,
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
        .select("price_per_night, currency_code, max_guests, name")
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
    currency_code = normalize_currency_code(room.data.get("currency_code"))
    currency_display_map = await get_currency_display_map(client, [currency_code])
    currency_display = resolve_currency_display(currency_code, currency_display_map)
    total_with_fees = round(total + taxes + service_fee, 2)

    await log_tool_call(
        client, property_id, session_id, "calculate_price",
        f"Calculated price for {room.data['name']}: "
        f"{_format_price_for_log(total_with_fees, currency_display)}",
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
        "total": total_with_fees,
        "currency": currency_code,
        "currency_code": currency_code,
        "currency_display": currency_display,
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

    # Fetch room metadata for widget display
    room_response = (
        client.table("rooms")
        .select("name, type, description, images, amenities, max_guests, bed_config")
        .eq("id", room_id)
        .eq("property_id", property_id)
        .single()
        .execute()
    )
    room_data = room_response.data or {}

    prop = await get_property_by_id(client, property_id)
    property_name = prop.get("name", "") if prop else ""

    # Get or create guest
    guest_id = await get_or_create_guest(client, property_id, guest_name, guest_email)
    if _is_valid_uuid(session_id):
        await link_session_to_guest(client, property_id, session_id, guest_id)

    # Create booking
    booking_data = {
        "property_id": property_id,
        "room_id": room_id,
        "guest_id": guest_id,
        "check_in": check_in,
        "check_out": check_out,
        "total_price": pricing["total"],
        "currency_code": pricing["currency_code"],
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
    await notify_booking_success(client, booking=booking, guest_name=guest_name)

    return {
        "booking_id": booking["id"],
        "status": booking_status,
        "guest_name": guest_name,
        "guests": guests,
        "room_id": room_id,
        "room_name": room_data.get("name", pricing.get("room_name", "")),
        "room_type": room_data.get("type", ""),
        "room_description": room_data.get("description", ""),
        "room_images": room_data.get("images", []),
        "amenities": room_data.get("amenities", []),
        "max_guests": room_data.get("max_guests"),
        "bed_config": room_data.get("bed_config", ""),
        "property_id": property_id,
        "property_name": property_name,
        "check_in": check_in,
        "check_out": check_out,
        "nights": pricing["nights"],
        "nightly_rate": pricing["nightly_rate"],
        "subtotal": pricing["subtotal"],
        "taxes": pricing["taxes"],
        "service_fee": pricing["service_fee"],
        "total": pricing["total"],
        "currency": pricing["currency"],
        "currency_code": pricing["currency_code"],
        "currency_display": pricing["currency_display"],
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
        "currency": booking["currency_code"],
        "currency_code": booking["currency_code"],
        "currency_display": booking["currency_display"],
    }


def _normalize_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _to_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _curated_maps_url(
    google_place_id: str | None,
    lat: float | None,
    lng: float | None,
) -> str | None:
    if google_place_id:
        return (
            "https://www.google.com/maps/search/?api=1"
            f"&query_place_id={google_place_id}"
        )
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return None


def _normalize_curated_place(row: dict[str, Any]) -> dict[str, Any]:
    lat = _to_float(row.get("lat")) if row.get("lat") is not None else None
    lng = _to_float(row.get("lng")) if row.get("lng") is not None else None
    photo_urls = _to_text_list(row.get("photo_urls"))
    return {
        "place_id": str(row.get("id", "")),
        "source": "curated",
        "name": row.get("name", ""),
        "address": row.get("address"),
        "lat": lat,
        "lng": lng,
        "rating": _to_float(row.get("rating")) if row.get("rating") is not None else None,
        "review_count": int(row["review_count"]) if row.get("review_count") is not None else None,
        "price_level": int(row["price_level"]) if row.get("price_level") is not None else None,
        "cuisine": _to_text_list(row.get("cuisine")),
        "phone": row.get("phone"),
        "website": row.get("website"),
        "photo_url": photo_urls[0] if photo_urls else None,
        "opening_hours": row.get("opening_hours"),
        "is_open_now": None,
        "walking_minutes": row.get("walking_minutes"),
        "distance_m": None,
        "best_for": _to_text_list(row.get("best_for")),
        "meal_types": _to_text_list(row.get("meal_types")),
        "is_curated": True,
        "is_sponsored": bool(row.get("sponsored", False)),
        "maps_url": _curated_maps_url(row.get("google_place_id"), lat, lng),
    }


def _with_distance(
    place: dict[str, Any],
    property_lat: float | None,
    property_lng: float | None,
) -> dict[str, Any]:
    if property_lat is None or property_lng is None:
        return place

    place_lat = place.get("lat")
    place_lng = place.get("lng")
    if place_lat is None or place_lng is None:
        return place

    distance_km = _haversine_distance_km(
        float(property_lat),
        float(property_lng),
        float(place_lat),
        float(place_lng),
    )
    distance_m = int(round(distance_km * 1000))
    walking_minutes = max(1, int(round(distance_m / 80)))

    enriched = dict(place)
    enriched["distance_m"] = distance_m
    if not enriched.get("walking_minutes"):
        enriched["walking_minutes"] = walking_minutes
    return enriched


async def search_places_nearby(
    client: Client,
    property_id: str,
    query: str = "restaurant",
    cuisine: str = "",
    price_level: int = 0,
    open_now: bool = False,
    limit: int = 8,
    meal_type: str = "",
    tags: str = "",
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    property_row = await get_property_by_id(client, property_id)
    if not property_row:
        return {"error": "Property not found"}

    property_lat = (
        _to_float(property_row.get("lat")) if property_row.get("lat") is not None else None
    )
    property_lng = (
        _to_float(property_row.get("lng")) if property_row.get("lng") is not None else None
    )
    safe_limit = max(1, min(int(limit or 8), 20))

    curated_rows = await list_curated_places(
        client,
        property_id,
        meal_type=meal_type or None,
        tags=tags or None,
        limit=max(safe_limit, 12),
    )

    filtered_curated: list[dict[str, Any]] = []
    requested_cuisine = cuisine.strip().lower()
    for row in curated_rows:
        if price_level and row.get("price_level") not in (None, price_level):
            continue
        if requested_cuisine:
            cuisines = [str(item).lower() for item in (row.get("cuisine") or [])]
            if requested_cuisine not in cuisines:
                continue
        filtered_curated.append(row)

    curated = [
        _with_distance(_normalize_curated_place(row), property_lat, property_lng)
        for row in filtered_curated[:safe_limit]
    ]

    nearby: list[dict[str, Any]] = []
    api_key = settings.google_places_api_key
    if api_key and property_lat is not None and property_lng is not None:
        google_results = await PlacesService.search_nearby(
            client=client,
            lat=float(property_lat),
            lng=float(property_lng),
            radius_m=settings.places_default_radius_m,
            query=query or "restaurant",
            cuisine=cuisine,
            price_level=price_level,
            open_now=open_now,
            limit=safe_limit + len(curated),
            api_key=api_key,
        )
        curated_google_ids = {
            str(row.get("google_place_id"))
            for row in filtered_curated
            if row.get("google_place_id")
        }
        deduped_google = [
            place
            for place in google_results
            if place.get("place_id") and place.get("place_id") not in curated_google_ids
        ]
        nearby = [
            _with_distance(place, property_lat, property_lng)
            for place in deduped_google[:safe_limit]
        ]

    result = {
        "property_id": property_id,
        "curated": curated,
        "nearby": nearby,
        "count_curated": len(curated),
        "count_nearby": len(nearby),
    }

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="search_places_nearby",
        description=f"Searched nearby places: '{query or 'restaurant'}'",
        status="success",
        source=source,
        request_payload={
            "query": query,
            "cuisine": cuisine,
            "price_level": price_level,
            "open_now": open_now,
            "limit": safe_limit,
            "meal_type": meal_type,
            "tags": _normalize_terms(tags),
        },
        response_payload={
            "count_curated": len(curated),
            "count_nearby": len(nearby),
        },
    )
    return result


async def get_curated_places(
    client: Client,
    property_id: str,
    meal_type: str = "",
    tags: str = "",
    limit: int = 5,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    property_row = await get_property_by_id(client, property_id)
    if not property_row:
        return {"error": "Property not found"}

    property_lat = (
        _to_float(property_row.get("lat")) if property_row.get("lat") is not None else None
    )
    property_lng = (
        _to_float(property_row.get("lng")) if property_row.get("lng") is not None else None
    )
    safe_limit = max(1, min(int(limit or 5), 20))

    rows = await list_curated_places(
        client,
        property_id,
        meal_type=meal_type or None,
        tags=tags or None,
        limit=safe_limit,
    )
    items = [
        _with_distance(_normalize_curated_place(row), property_lat, property_lng)
        for row in rows
    ]

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="get_curated_places",
        description="Retrieved curated places list",
        status="success",
        source=source,
        request_payload={
            "meal_type": meal_type,
            "tags": _normalize_terms(tags),
            "limit": safe_limit,
        },
        response_payload={"count": len(items)},
    )

    return {
        "property_id": property_id,
        "curated": items,
        "nearby": [],
        "count_curated": len(items),
        "count_nearby": 0,
    }


def _normalize_slot_time_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip()
    if not normalized:
        return ""
    parts = normalized.split(":")
    if len(parts) >= 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    return normalized


def _service_is_slot_based(service: dict[str, Any]) -> bool:
    capacity_mode = str(service.get("capacity_mode") or "").lower()
    availability_type = str(service.get("availability_type") or "").lower()
    return capacity_mode in {"per_hour_limit", "slot_based"} or availability_type == "time_slot"


def _service_capacity_limit(service: dict[str, Any]) -> int:
    raw = service.get("capacity_limit")
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _service_slot_capacity(slot: dict[str, Any]) -> int:
    raw = slot.get("capacity")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _service_slot_booked(slot: dict[str, Any]) -> int:
    raw = slot.get("booked")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _service_public_and_active(service: dict[str, Any]) -> bool:
    status = str(service.get("status") or "").lower()
    visibility = str(service.get("visibility") or "").lower()
    return status == "active" and visibility == "public"


async def _get_property_team_emails(client: Client, property_id: str) -> list[str]:
    account_id = await get_account_id_for_property(client, property_id)
    if not account_id:
        return []

    members_response = (
        client.table("team_members")
        .select("user_id")
        .eq("account_id", account_id)
        .eq("status", "accepted")
        .is_("deleted_at", "null")
        .execute()
    )
    user_ids = []
    for row in members_response.data or []:
        user_id = row.get("user_id")
        if user_id and user_id not in user_ids:
            user_ids.append(user_id)
    if not user_ids:
        return []

    users_response = client.table("users").select("email").in_("id", user_ids).execute()
    emails = []
    for row in users_response.data or []:
        email = str(row.get("email") or "").strip()
        if email and email not in emails:
            emails.append(email)
    return emails


def _service_category_matches(service: dict[str, Any], category: str) -> bool:
    normalized = category.strip().lower()
    if not normalized:
        return True

    if _is_valid_uuid(category):
        return str(service.get("category_id") or "") == category

    category_name = str(service.get("category_name") or "").strip().lower()
    return category_name == normalized


async def list_services_tool(
    client: Client,
    property_id: str,
    search: str = "",
    category: str = "",
    limit: int = 20,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    """List active public services available for guests."""
    safe_limit = max(1, min(int(limit or 20), 100))
    services = await list_services(
        client,
        property_id,
        search=search or None,
        category_id=category if _is_valid_uuid(category) else None,
        status_filter="active",
    )

    filtered = [
        service
        for service in services
        if str(service.get("visibility") or "").lower() == "public"
    ]
    if category and not _is_valid_uuid(category):
        filtered = [service for service in filtered if _service_category_matches(service, category)]

    filtered = filtered[:safe_limit]
    currency_display_map = await get_currency_display_map(
        client, [service.get("currency_code") for service in filtered]
    )

    normalized_services = []
    for service in filtered:
        currency_code = normalize_currency_code(service.get("currency_code"))
        normalized_services.append(
            {
                "id": service.get("id"),
                "name": service.get("name"),
                "short_description": service.get("short_description") or "",
                "full_description": service.get("full_description") or "",
                "image_urls": service.get("image_urls") or [],
                "category_id": service.get("category_id"),
                "category_name": service.get("category_name"),
                "partner_id": service.get("partner_id"),
                "partner_name": service.get("partner_name"),
                "price": _to_float(service.get("price")),
                "pricing_type": service.get("pricing_type") or "fixed",
                "currency_code": currency_code,
                "currency_display": resolve_currency_display(currency_code, currency_display_map),
                "availability_type": service.get("availability_type") or "always",
                "capacity_mode": service.get("capacity_mode") or "unlimited",
                "capacity_limit": service.get("capacity_limit"),
                "slots": service.get("slots") or [],
            }
        )

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="list_services",
        description="Listed active public services",
        status="success",
        source=source,
        request_payload={"search": search, "category": category, "limit": safe_limit},
        response_payload={"count": len(normalized_services)},
    )

    return {
        "property_id": property_id,
        "services": normalized_services,
        "count": len(normalized_services),
    }


async def get_service_details_tool(
    client: Client,
    property_id: str,
    service_id: str,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    """Get details for a single service."""
    service = await get_service_by_id(client, property_id, service_id)
    if not service:
        return {"error": "Service not found."}

    currency_code = normalize_currency_code(service.get("currency_code"))
    currency_display_map = await get_currency_display_map(client, [currency_code])

    result = {
        **service,
        "price": _to_float(service.get("price")),
        "currency_code": currency_code,
        "currency_display": resolve_currency_display(currency_code, currency_display_map),
        "slots": service.get("slots") or [],
    }

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="get_service_details",
        description=f"Retrieved service details: {service_id}",
        status="success",
        source=source,
        request_payload={"service_id": service_id},
        response_payload={"found": True},
    )

    return {"service": result}


async def check_service_availability_tool(
    client: Client,
    property_id: str,
    service_id: str,
    service_date: str,
    quantity: int = 1,
    slot_time: str | None = None,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    """Check whether a service can be booked for the requested date/quantity."""
    if quantity <= 0:
        return {"available": False, "error": "quantity must be greater than 0."}

    try:
        normalized_service_date = date.fromisoformat(service_date).isoformat()
    except ValueError:
        return {"available": False, "error": "service_date must be in YYYY-MM-DD format."}

    service = await get_service_by_id(client, property_id, service_id)
    if not service:
        return {"available": False, "error": "Service not found."}
    if not _service_public_and_active(service):
        return {"available": False, "error": "Service is not active and public."}

    capacity_mode = str(service.get("capacity_mode") or "unlimited").lower()
    is_slot_based = _service_is_slot_based(service)
    availability: dict[str, Any] = {
        "available": True,
        "service_id": service_id,
        "service_date": normalized_service_date,
        "quantity": quantity,
        "capacity_mode": capacity_mode,
    }

    if capacity_mode == "unlimited" and not is_slot_based:
        await log_tool_call(
            client=client,
            property_id=property_id,
            session_id=session_id,
            tool_name="check_service_availability",
            description=f"Checked service availability for {service_id}: available",
            status="success",
            source=source,
            request_payload={
                "service_id": service_id,
                "service_date": normalized_service_date,
                "quantity": quantity,
                "slot_time": slot_time,
            },
            response_payload={"available": True, "capacity_mode": capacity_mode},
        )
        return availability

    if is_slot_based:
        slots = service.get("slots") if isinstance(service.get("slots"), list) else []
        requested_slot_key = _normalize_slot_time_key(slot_time)
        selected_slot: dict[str, Any] | None = None

        if requested_slot_key:
            for slot in slots:
                if _normalize_slot_time_key(str(slot.get("time") or "")) == requested_slot_key:
                    selected_slot = slot
                    break
        else:
            for slot in slots:
                slot_capacity = _service_slot_capacity(slot)
                slot_booked = _service_slot_booked(slot)
                if slot_capacity <= 0 or slot_booked + quantity <= slot_capacity:
                    selected_slot = slot
                    break

        if not selected_slot:
            availability.update(
                {
                    "available": False,
                    "error": "No available service slot for the requested quantity.",
                    "slots": slots,
                }
            )
        else:
            slot_capacity = _service_slot_capacity(selected_slot)
            slot_booked = _service_slot_booked(selected_slot)
            slot_remaining = max(slot_capacity - slot_booked, 0) if slot_capacity > 0 else None
            availability.update(
                {
                    "slot_id": selected_slot.get("id"),
                    "slot_time": selected_slot.get("time"),
                    "slot_capacity": slot_capacity,
                    "slot_booked": slot_booked,
                    "slot_remaining": slot_remaining,
                    "available": slot_capacity <= 0 or slot_booked + quantity <= slot_capacity,
                }
            )
            if not availability["available"]:
                availability["error"] = "Requested quantity exceeds slot capacity."

        await log_tool_call(
            client=client,
            property_id=property_id,
            session_id=session_id,
            tool_name="check_service_availability",
            description=(
                f"Checked slot availability for service {service_id}: "
                f"{'available' if availability.get('available') else 'unavailable'}"
            ),
            status="success",
            source=source,
            request_payload={
                "service_id": service_id,
                "service_date": normalized_service_date,
                "quantity": quantity,
                "slot_time": slot_time,
            },
            response_payload={
                "available": availability.get("available", False),
                "slot_time": availability.get("slot_time"),
            },
        )
        return availability

    if capacity_mode in {"limited_quantity", "per_day_limit"}:
        capacity_limit = _service_capacity_limit(service)
        query = (
            client.table("service_bookings")
            .select("quantity")
            .eq("property_id", property_id)
            .eq("service_id", service_id)
            .neq("status", "cancelled")
        )
        if capacity_mode == "per_day_limit":
            query = query.eq("service_date", normalized_service_date)
        bookings_response = query.execute()
        booked_quantity = sum(int(row.get("quantity") or 0) for row in bookings_response.data or [])
        remaining = max(capacity_limit - booked_quantity, 0)
        available = capacity_limit > 0 and booked_quantity + quantity <= capacity_limit

        availability.update(
            {
                "available": available,
                "capacity_limit": capacity_limit,
                "booked_quantity": booked_quantity,
                "remaining_quantity": remaining,
            }
        )
        if capacity_limit <= 0:
            availability["available"] = False
            availability["error"] = "Service capacity_limit is not configured."
        elif not available:
            availability["error"] = "Requested quantity exceeds remaining capacity."

        await log_tool_call(
            client=client,
            property_id=property_id,
            session_id=session_id,
            tool_name="check_service_availability",
            description=(
                f"Checked quantity availability for service {service_id}: "
                f"{'available' if availability.get('available') else 'unavailable'}"
            ),
            status="success",
            source=source,
            request_payload={
                "service_id": service_id,
                "service_date": normalized_service_date,
                "quantity": quantity,
                "slot_time": slot_time,
            },
            response_payload={
                "available": availability.get("available", False),
                "remaining_quantity": availability.get("remaining_quantity"),
            },
        )
        return availability

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="check_service_availability",
        description=f"Checked service availability for {service_id}: available",
        status="success",
        source=source,
        request_payload={
            "service_id": service_id,
            "service_date": normalized_service_date,
            "quantity": quantity,
            "slot_time": slot_time,
        },
        response_payload={"available": True, "capacity_mode": capacity_mode},
    )
    return availability


async def create_service_booking_tool(
    client: Client,
    property_id: str,
    service_id: str,
    guest_name: str,
    service_date: str,
    quantity: int = 1,
    guest_email: str | None = None,
    slot_time: str | None = None,
    session_id: str | None = None,
    source: str = "widget",
    booking_status: str = "confirmed",
) -> dict[str, Any]:
    """Create a service booking after availability check."""
    _ = guest_email
    cleaned_guest_name = (guest_name or "").strip()
    if not cleaned_guest_name:
        return {"error": "guest_name is required."}
    if quantity <= 0:
        return {"error": "quantity must be greater than 0."}
    try:
        normalized_service_date = date.fromisoformat(service_date).isoformat()
    except ValueError:
        return {"error": "service_date must be in YYYY-MM-DD format."}

    service = await get_service_by_id(client, property_id, service_id)
    if not service:
        return {"error": "Service not found."}
    if not _service_public_and_active(service):
        return {"error": "Service is not available for booking."}

    availability = await check_service_availability_tool(
        client=client,
        property_id=property_id,
        service_id=service_id,
        service_date=normalized_service_date,
        quantity=quantity,
        slot_time=slot_time,
        session_id=session_id,
        source=source,
    )
    if not availability.get("available"):
        return {"error": availability.get("error", "Service is not available."), "availability": availability}

    unit_price = _to_float(service.get("price"))
    total = round(unit_price * quantity, 2)
    currency_code = normalize_currency_code(service.get("currency_code"))
    external_ref = f"SB-{_uuid.uuid4().hex[:10].upper()}"

    booking_payload = {
        "property_id": property_id,
        "service_id": service_id,
        "external_ref": external_ref,
        "guest_name": cleaned_guest_name,
        "service_date": normalized_service_date,
        "quantity": quantity,
        "total": total,
        "currency_code": currency_code,
        "status": booking_status,
    }

    inserted = client.table("service_bookings").insert(booking_payload).execute()
    created = inserted.data[0] if inserted.data else None
    if not created:
        return {"error": "Failed to create service booking."}

    selected_slot_id = availability.get("slot_id")
    selected_slot_time = availability.get("slot_time")
    if selected_slot_id:
        slot_booked = int(availability.get("slot_booked") or 0)
        updated_booked = max(0, slot_booked + quantity)
        (
            client.table("service_time_slots")
            .update({"booked": updated_booked})
            .eq("id", selected_slot_id)
            .eq("service_id", service_id)
            .execute()
        )

    await notify_service_booking_success(
        client,
        booking={
            **created,
            "quantity": quantity,
            "total": total,
            "currency_code": currency_code,
        },
        service_name=str(service.get("name") or ""),
    )

    try:
        recipients = await _get_property_team_emails(client, property_id)
        await send_service_booking_email(
            recipients=recipients,
            service_name=str(service.get("name") or "Service"),
            guest_name=cleaned_guest_name,
            service_date=normalized_service_date,
            quantity=quantity,
            total=total,
            currency_code=currency_code,
            external_ref=external_ref,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send service booking email: %s", exc)

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="create_service_booking",
        description=f"Created service booking for {cleaned_guest_name}",
        status="success",
        source=source,
        request_payload={
            "service_id": service_id,
            "service_date": normalized_service_date,
            "quantity": quantity,
            "slot_time": slot_time,
        },
        response_payload={"service_booking_id": created.get("id"), "total": total},
    )

    return {
        "booking_id": created.get("id"),
        "external_ref": external_ref,
        "status": booking_status,
        "service_id": service_id,
        "service_name": service.get("name"),
        "guest_name": cleaned_guest_name,
        "service_date": normalized_service_date,
        "quantity": quantity,
        "unit_price": unit_price,
        "total": total,
        "currency_code": currency_code,
        "slot_time": selected_slot_time,
        "message": f"Service booked successfully. Reference: {external_ref}",
    }


async def cancel_service_booking_tool(
    client: Client,
    property_id: str,
    service_booking_id: str,
    slot_time: str | None = None,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    """Cancel an existing service booking."""
    response = (
        client.table("service_bookings")
        .select("*")
        .eq("id", service_booking_id)
        .eq("property_id", property_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return {"error": "Service booking not found."}

    booking = response.data[0]
    current_status = str(booking.get("status") or "").lower()
    if current_status == "cancelled":
        return {
            "service_booking_id": service_booking_id,
            "status": "cancelled",
            "message": "Service booking is already cancelled.",
        }

    (
        client.table("service_bookings")
        .update({"status": "cancelled", "updated_at": datetime.utcnow().isoformat()})
        .eq("id", service_booking_id)
        .eq("property_id", property_id)
        .execute()
    )

    decremented_slot_time: str | None = None
    service_id = str(booking.get("service_id") or "")
    service = await get_service_by_id(client, property_id, service_id)
    if service and _service_is_slot_based(service):
        slots = service.get("slots") if isinstance(service.get("slots"), list) else []
        target_slot: dict[str, Any] | None = None
        normalized_slot_key = _normalize_slot_time_key(slot_time)

        if normalized_slot_key:
            for slot in slots:
                if _normalize_slot_time_key(str(slot.get("time") or "")) == normalized_slot_key:
                    target_slot = slot
                    break
        if target_slot is None:
            for slot in slots:
                if _service_slot_booked(slot) > 0:
                    target_slot = slot
                    break

        if target_slot and target_slot.get("id"):
            updated_booked = max(
                0,
                _service_slot_booked(target_slot) - int(booking.get("quantity") or 1),
            )
            (
                client.table("service_time_slots")
                .update({"booked": updated_booked})
                .eq("id", target_slot["id"])
                .eq("service_id", service_id)
                .execute()
            )
            decremented_slot_time = str(target_slot.get("time") or "")

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="cancel_service_booking",
        description=f"Cancelled service booking {service_booking_id}",
        status="success",
        source=source,
        request_payload={
            "service_booking_id": service_booking_id,
            "slot_time": slot_time,
        },
        response_payload={"status": "cancelled", "decremented_slot_time": decremented_slot_time},
    )

    return {
        "service_booking_id": service_booking_id,
        "status": "cancelled",
        "decremented_slot_time": decremented_slot_time,
        "message": "Service booking cancelled successfully.",
    }


async def search_service_kb_tool(
    client: Client,
    property_id: str,
    api_key: str,
    query: str,
    limit: int = 5,
    threshold: float = 0.6,
    session_id: str | None = None,
    source: str = "widget",
) -> dict[str, Any]:
    """Semantic search over service-related knowledge chunks."""
    safe_limit = max(1, min(int(limit or 5), 20))
    results = await search_similar(
        client=client,
        property_id=property_id,
        query=query,
        api_key=api_key,
        limit=safe_limit,
        threshold=threshold,
    )

    knowledge_results = [
        row
        for row in results
        if str(row.get("source_type") or "") == "knowledge_chunk"
    ]

    formatted = [
        {
            "content": row.get("content", ""),
            "source_type": row.get("source_type"),
            "source_id": row.get("source_id"),
            "similarity": round(float(row.get("similarity") or 0), 3),
            "file_name": (row.get("metadata") or {}).get("file_name", ""),
            "section": (row.get("metadata") or {}).get("section", ""),
        }
        for row in knowledge_results
    ]

    await log_tool_call(
        client=client,
        property_id=property_id,
        session_id=session_id,
        tool_name="search_service_kb",
        description=f"Searched service knowledge: '{query}'",
        status="success",
        source=source,
        request_payload={"query": query, "limit": safe_limit, "threshold": threshold},
        response_payload={"count": len(formatted)},
    )

    return {
        "results": formatted,
        "count": len(formatted),
    }
