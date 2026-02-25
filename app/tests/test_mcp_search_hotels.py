from __future__ import annotations

import asyncio
import copy
from datetime import date, timedelta
from unittest.mock import AsyncMock

from app.agents.tools import search_hotels
import app.mcp.server as mcp_server


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name: str, storage: dict[str, list[dict]]):
        self.table_name = table_name
        self.storage = storage
        self.filters: list = []
        self.insert_payload = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(lambda row: row.get(field) == value)
        return self

    def neq(self, field, value):
        self.filters.append(lambda row: row.get(field) != value)
        return self

    def in_(self, field, values):
        accepted = set(values)
        self.filters.append(lambda row: row.get(field) in accepted)
        return self

    def lt(self, field, value):
        self.filters.append(lambda row: row.get(field) < value)
        return self

    def gt(self, field, value):
        self.filters.append(lambda row: row.get(field) > value)
        return self

    def gte(self, field, value):
        self.filters.append(lambda row: row.get(field) >= value)
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def execute(self):
        if self.insert_payload is not None:
            target = self.storage.setdefault(self.table_name, [])
            if isinstance(self.insert_payload, list):
                for row in self.insert_payload:
                    target.append(copy.deepcopy(row))
                return FakeResponse(copy.deepcopy(self.insert_payload))
            target.append(copy.deepcopy(self.insert_payload))
            return FakeResponse([copy.deepcopy(self.insert_payload)])

        rows = [
            copy.deepcopy(row)
            for row in self.storage.get(self.table_name, [])
            if all(predicate(row) for predicate in self.filters)
        ]
        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, storage: dict[str, list[dict]]):
        self.storage = storage

    def table(self, table_name: str):
        return FakeTableQuery(table_name, self.storage)


def _future_stay_dates() -> tuple[str, str]:
    check_in_date = date.today() + timedelta(days=30)
    check_out_date = check_in_date + timedelta(days=2)
    return check_in_date.isoformat(), check_out_date.isoformat()


def _build_storage() -> dict[str, list[dict]]:
    check_in, check_out = _future_stay_dates()
    return {
        "properties": [
            {
                "id": "prop-1",
                "city": "Volosyanka",
                "country": "Ukraine",
                "lat": 48.8470,
                "lng": 23.4219,
                "description": "Mountain hotel near ski slopes",
                "accounts": {"name": "Volosyanka Hills Hotel"},
            },
            {
                "id": "prop-2",
                "city": "Lviv",
                "country": "Ukraine",
                "lat": 49.8397,
                "lng": 24.0297,
                "description": "Downtown city stay",
                "accounts": {"name": "Lviv Central Stay"},
            },
            {
                "id": "prop-3",
                "city": "Zakopane",
                "country": "Poland",
                "lat": 49.2992,
                "lng": 19.9496,
                "description": "Polish mountain retreat",
                "accounts": {"name": "Tatry Lodge"},
            },
        ],
        "rooms": [
            {
                "id": "room-1",
                "property_id": "prop-1",
                "name": "Panorama Suite",
                "type": "Suite",
                "description": "Mountain view suite",
                "price_per_night": 120,
                "max_guests": 2,
                "amenities": ["WiFi", "Pet Friendly", "Balcony"],
                "images": [],
                "status": "active",
            },
            {
                "id": "room-2",
                "property_id": "prop-1",
                "name": "Family Loft",
                "type": "Family Room",
                "description": "Large room for families",
                "price_per_night": 180,
                "max_guests": 5,
                "amenities": ["WiFi", "Kitchen"],
                "images": [],
                "status": "active",
            },
            {
                "id": "room-3",
                "property_id": "prop-2",
                "name": "City Compact",
                "type": "Standard Room",
                "description": "Compact city room",
                "price_per_night": 90,
                "max_guests": 2,
                "amenities": ["WiFi"],
                "images": [],
                "status": "active",
            },
            {
                "id": "room-4",
                "property_id": "prop-3",
                "name": "Tatry Deluxe",
                "type": "Deluxe",
                "description": "Mountain deluxe room",
                "price_per_night": 200,
                "max_guests": 3,
                "amenities": ["WiFi"],
                "images": [],
                "status": "active",
            },
        ],
        "bookings": [
            {
                "id": "booking-1",
                "room_id": "room-1",
                "status": "confirmed",
                "check_in": check_in,
                "check_out": check_out,
            },
            {
                "id": "booking-2",
                "room_id": "room-2",
                "status": "cancelled",
                "check_in": check_in,
                "check_out": check_out,
            },
        ],
        "room_guest_tiers": [
            {
                "room_id": "room-2",
                "min_guests": 1,
                "max_guests": 2,
                "price_per_night": 150,
            },
            {
                "room_id": "room-2",
                "min_guests": 3,
                "max_guests": 5,
                "price_per_night": 220,
            },
        ],
        "room_date_pricing": [
            {
                "room_id": "room-2",
                "date": check_in,
                "price": 300,
            },
            {
                "room_id": "room-3",
                "date": check_in,
                "price": 150,
            },
        ],
        "audit_log": [],
    }


def _build_client() -> tuple[FakeSupabaseClient, dict[str, list[dict]]]:
    storage = _build_storage()
    return FakeSupabaseClient(storage), storage


def _run(coro):
    return asyncio.run(coro)


def test_search_hotels_filters_by_city_country_property_and_room_name():
    client, _ = _build_client()

    result = _run(
        search_hotels(
            client=client,
            city="volosyanka",
            country="ukraine",
            property_name="hills",
            room_name="panorama",
        )
    )

    assert result["count_hotels"] == 1
    assert result["count_rooms"] == 1
    assert result["hotels"][0]["property_id"] == "prop-1"
    assert result["hotels"][0]["matching_rooms"][0]["id"] == "room-1"


def test_search_hotels_coordinate_filter_uses_default_20km_radius():
    client, _ = _build_client()

    result = _run(
        search_hotels(
            client=client,
            lat=48.8470,
            lng=23.4219,
        )
    )

    assert result["count_hotels"] == 1
    assert result["hotels"][0]["property_id"] == "prop-1"
    assert result["hotels"][0]["distance_km"] == 0.0
    assert result["applied_filters"]["radius_km"] == 20.0


def test_search_hotels_filters_by_guest_capacity():
    client, _ = _build_client()

    result = _run(search_hotels(client=client, city="Volosyanka", guests=4))

    assert result["count_hotels"] == 1
    assert result["count_rooms"] == 1
    assert result["hotels"][0]["matching_rooms"][0]["id"] == "room-2"


def test_search_hotels_filters_pet_friendly_rooms():
    client, _ = _build_client()

    result = _run(
        search_hotels(client=client, city="Volosyanka", pet_friendly=True)
    )

    assert result["count_hotels"] == 1
    assert result["count_rooms"] == 1
    assert result["hotels"][0]["matching_rooms"][0]["id"] == "room-1"
    assert result["hotels"][0]["pet_friendly_option"] is True


def test_search_hotels_applies_availability_filter_only_non_cancelled_conflicts():
    client, _ = _build_client()
    check_in, check_out = _future_stay_dates()

    result = _run(
        search_hotels(
            client=client,
            city="Volosyanka",
            check_in=check_in,
            check_out=check_out,
        )
    )

    assert result["count_hotels"] == 1
    assert result["count_rooms"] == 1
    assert result["hotels"][0]["matching_rooms"][0]["id"] == "room-2"


def test_search_hotels_applies_budget_per_night():
    client, _ = _build_client()

    result = _run(
        search_hotels(
            client=client,
            country="Ukraine",
            budget_per_night_max=100,
        )
    )

    assert result["count_hotels"] == 1
    assert result["hotels"][0]["property_id"] == "prop-2"
    assert result["hotels"][0]["matching_rooms"][0]["id"] == "room-3"


def test_search_hotels_applies_budget_total_with_guest_tiers_and_date_overrides():
    client, _ = _build_client()
    check_in, check_out = _future_stay_dates()

    result = _run(
        search_hotels(
            client=client,
            city="Volosyanka",
            guests=4,
            check_in=check_in,
            check_out=check_out,
            budget_total_max=610,
        )
    )

    assert result["count_hotels"] == 1
    room = result["hotels"][0]["matching_rooms"][0]
    assert room["id"] == "room-2"
    assert room["estimated_total_price"] == 603.2

    result_tight_budget = _run(
        search_hotels(
            client=client,
            city="Volosyanka",
            guests=4,
            check_in=check_in,
            check_out=check_out,
            budget_total_max=600,
        )
    )
    assert result_tight_budget["count_hotels"] == 0


def test_search_hotels_validation_requires_both_dates():
    client, _ = _build_client()
    check_in, _ = _future_stay_dates()

    result = _run(search_hotels(client=client, city="Volosyanka", check_in=check_in))

    assert result["error"] == "Both check_in and check_out must be provided together."


def test_search_hotels_validation_requires_lat_lng_pair():
    client, _ = _build_client()

    result = _run(search_hotels(client=client, city="Volosyanka", lat=48.8))

    assert result["error"] == "Both lat and lng must be provided together."


def test_search_hotels_validation_rejects_invalid_budget():
    client, _ = _build_client()

    result = _run(search_hotels(client=client, city="Volosyanka", budget_per_night_max=0))

    assert result["error"] == "budget_per_night_max must be greater than 0."


def test_search_hotels_validation_rejects_invalid_guests():
    client, _ = _build_client()

    result = _run(search_hotels(client=client, city="Volosyanka", guests=0))

    assert result["error"] == "Guest count must be at least 1."


def test_search_hotels_validation_requires_dates_for_total_budget():
    client, _ = _build_client()

    result = _run(search_hotels(client=client, city="Volosyanka", budget_total_max=500))

    assert result["error"] == "budget_total_max requires both check_in and check_out dates."


def test_mcp_search_hotels_wrapper_success(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_supabase_client", lambda: object())
    search_hotels_mock = AsyncMock(
        return_value={
            "hotels": [{"property_id": "prop-1", "matching_rooms": []}],
            "count_hotels": 1,
            "count_rooms": 0,
            "applied_filters": {"city": "Volosyanka"},
            "message": "Found 1 hotel(s) with 0 matching room(s).",
        }
    )
    monkeypatch.setattr(mcp_server, "search_hotels", search_hotels_mock)

    result = _run(mcp_server.mcp_search_hotels(city="Volosyanka"))

    assert result["structuredContent"]["count_hotels"] == 1
    assert result["content"][0]["text"] == "Found 1 hotel(s)."
    assert result["_meta"]["monobook/widget"] == "search_hotels"
    assert search_hotels_mock.await_args.kwargs["source"] == "chatgpt"


def test_mcp_search_hotels_wrapper_returns_tool_error(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_supabase_client", lambda: object())
    monkeypatch.setattr(
        mcp_server,
        "search_hotels",
        AsyncMock(return_value={"error": "validation failed"}),
    )

    result = _run(mcp_server.mcp_search_hotels(city="Volosyanka"))

    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "validation failed"
    assert result["_meta"]["monobook/widget"] == "search_hotels"
