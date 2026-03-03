from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.db.base import get_supabase
import app.api.routes.rooms as room_routes

rooms_test_app = FastAPI()
rooms_test_app.include_router(room_routes.router)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name: str, storage: dict[str, list[dict]]):
        self.table_name = table_name
        self.storage = storage
        self.filters: list[tuple[str, object]] = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field: str, value: object):
        self.filters.append((field, value))
        return self

    def execute(self):
        rows = [
            row
            for row in self.storage.get(self.table_name, [])
            if all(row.get(field) == value for field, value in self.filters)
        ]
        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, storage: dict[str, list[dict]]):
        self.storage = storage

    def table(self, table_name: str):
        return FakeTableQuery(table_name, self.storage)


def _override_current_user():
    return {"id": "user-1", "email": "user@example.com"}


def _room_response(
    *,
    source: str,
    source_url: str,
    currency_code: str = "USD",
) -> dict:
    return {
        "id": "room-1",
        "property_id": "prop-1",
        "name": "Imported Room",
        "type": "Apartment",
        "description": "Imported listing description",
        "images": ["https://example.com/image.jpg"],
        "price_per_night": 200.0,
        "currency_code": currency_code,
        "currency_display": currency_code,
        "max_guests": 4,
        "bed_config": "1 King Bed",
        "amenities": ["WiFi"],
        "source": source,
        "source_url": source_url,
        "sync_enabled": False,
        "last_synced": None,
        "status": "active",
        "created_at": "2026-03-03T10:00:00Z",
        "updated_at": "2026-03-03T10:00:00Z",
        "guest_tiers": [],
        "date_overrides": [],
    }


def test_import_booking_url_success(monkeypatch):
    storage = {"rooms": []}
    rooms_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    rooms_test_app.dependency_overrides[get_supabase] = lambda: FakeSupabaseClient(storage)

    create_room_mock = AsyncMock(
        return_value=_room_response(
            source="booking",
            source_url="https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html",
            currency_code="GBP",
        )
    )
    scrape_booking_mock = AsyncMock(
        return_value=SimpleNamespace(
            name="Cheval Three Quays",
            type="Apartment",
            description="Luxury serviced apartment",
            images=["https://example.com/photo.jpg"],
            price_per_night=450.0,
            currency_code="GBP",
            max_guests=4,
            bed_config="1 King Bed",
            amenities=["WiFi", "Parking"],
        )
    )

    monkeypatch.setattr(room_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(room_routes, "validate_booking_url", lambda _url: create_room_mock.return_value["source_url"])
    monkeypatch.setattr(room_routes, "scrape_booking_listing", scrape_booking_mock)
    monkeypatch.setattr(room_routes, "create_room", create_room_mock)

    try:
        with TestClient(rooms_test_app) as client:
            response = client.post(
                "/v1.0/properties/prop-1/rooms/import",
                json={"url": "https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html?aid=42"},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["source"] == "booking"
        assert body["currency_code"] == "GBP"
        assert body["source_url"] == "https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html"

        payload = create_room_mock.await_args.args[2]
        assert payload["source"] == "booking"
        assert payload["currency_code"] == "GBP"
        assert payload["source_url"] == "https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html"
        assert payload["name"] == "Cheval Three Quays"
        assert scrape_booking_mock.await_count == 1
    finally:
        rooms_test_app.dependency_overrides = {}


def test_import_airbnb_url_still_supported(monkeypatch):
    storage = {"rooms": []}
    rooms_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    rooms_test_app.dependency_overrides[get_supabase] = lambda: FakeSupabaseClient(storage)

    canonical = "https://www.airbnb.com/rooms/12345678"
    create_room_mock = AsyncMock(
        return_value=_room_response(source="airbnb", source_url=canonical)
    )
    scrape_airbnb_mock = AsyncMock(
        return_value=SimpleNamespace(
            name="Airbnb Room",
            type="Entire home",
            description="Nice place",
            images=["https://example.com/a.jpg"],
            price_per_night=150.0,
            max_guests=2,
            bed_config="1 Bed",
            amenities=["WiFi"],
        )
    )

    monkeypatch.setattr(room_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(room_routes, "validate_airbnb_url", lambda _url: canonical)
    monkeypatch.setattr(room_routes, "scrape_airbnb_listing", scrape_airbnb_mock)
    monkeypatch.setattr(room_routes, "create_room", create_room_mock)

    try:
        with TestClient(rooms_test_app) as client:
            response = client.post(
                "/v1.0/properties/prop-1/rooms/import",
                json={"url": "https://www.airbnb.com/rooms/12345678"},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["source"] == "airbnb"
        payload = create_room_mock.await_args.args[2]
        assert payload["source"] == "airbnb"
        assert payload["currency_code"] == "USD"
        assert scrape_airbnb_mock.await_count == 1
    finally:
        rooms_test_app.dependency_overrides = {}


def test_import_duplicate_booking_url_returns_conflict(monkeypatch):
    canonical = "https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html"
    storage = {
        "rooms": [
            {
                "id": "room-existing",
                "property_id": "prop-1",
                "source_url": canonical,
            }
        ]
    }
    rooms_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    rooms_test_app.dependency_overrides[get_supabase] = lambda: FakeSupabaseClient(storage)

    scrape_booking_mock = AsyncMock()

    monkeypatch.setattr(room_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(room_routes, "validate_booking_url", lambda _url: canonical)
    monkeypatch.setattr(room_routes, "scrape_booking_listing", scrape_booking_mock)

    try:
        with TestClient(rooms_test_app) as client:
            response = client.post(
                "/v1.0/properties/prop-1/rooms/import",
                json={"url": "https://www.booking.com/hotel/gb/cheval-three-quays.en-gb.html"},
            )

        assert response.status_code == 409
        assert "Booking.com listing has already been imported" in response.json()["detail"]
        assert scrape_booking_mock.await_count == 0
    finally:
        rooms_test_app.dependency_overrides = {}


def test_import_unsupported_platform_url_returns_bad_request(monkeypatch):
    storage = {"rooms": []}
    rooms_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    rooms_test_app.dependency_overrides[get_supabase] = lambda: FakeSupabaseClient(storage)

    monkeypatch.setattr(room_routes, "user_owns_property", AsyncMock(return_value=True))

    try:
        with TestClient(rooms_test_app) as client:
            response = client.post(
                "/v1.0/properties/prop-1/rooms/import",
                json={"url": "https://example.com/hotel/abc"},
            )

        assert response.status_code == 400
        assert "Unsupported listing URL" in response.json()["detail"]
    finally:
        rooms_test_app.dependency_overrides = {}


def test_import_booking_scrape_error_returns_unprocessable(monkeypatch):
    storage = {"rooms": []}
    rooms_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    rooms_test_app.dependency_overrides[get_supabase] = lambda: FakeSupabaseClient(storage)

    monkeypatch.setattr(room_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(
        room_routes,
        "validate_booking_url",
        lambda _url: "https://www.booking.com/hotel/gb/example.en-gb.html",
    )
    monkeypatch.setattr(
        room_routes,
        "scrape_booking_listing",
        AsyncMock(side_effect=ValueError("Could not extract listing details")),
    )

    try:
        with TestClient(rooms_test_app) as client:
            response = client.post(
                "/v1.0/properties/prop-1/rooms/import",
                json={"url": "https://www.booking.com/hotel/gb/example.en-gb.html"},
            )

        assert response.status_code == 422
        assert response.json()["detail"] == "Could not extract listing details"
    finally:
        rooms_test_app.dependency_overrides = {}
