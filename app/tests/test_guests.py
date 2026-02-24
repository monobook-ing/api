from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.db.base import get_supabase
import app.api.routes.guests as guest_routes
from app.crud.guest import _extract_first_room_image, _map_latest_booking

guest_test_app = FastAPI()
guest_test_app.include_router(guest_routes.router)


def _override_current_user():
    return {"id": "user-1", "email": "user@example.com"}


def _sample_guest_detail() -> dict:
    return {
        "id": "guest-1",
        "property_id": "prop-1",
        "name": "Sarah Chen",
        "email": "sarah@example.com",
        "phone": "+1 415-555-0142",
        "notes": "VIP",
        "total_stays": 2,
        "last_stay_date": "2026-02-20",
        "total_spent": 1298.0,
        "latest_booking": {
            "id": "booking-1",
            "room_id": "room-1",
            "room_image": "https://cdn.example.com/room-1-main.jpg",
            "room_name": "Ocean View Deluxe Suite",
            "check_in": "2026-02-18",
            "check_out": "2026-02-20",
            "status": "confirmed",
            "total_price": 578.0,
            "ai_handled": True,
            "source": "chatgpt",
        },
        "created_at": "2026-02-01T10:00:00+00:00",
        "updated_at": "2026-02-21T10:00:00+00:00",
        "bookings": [
            {
                "id": "booking-1",
                "guest_id": "guest-1",
                "room_id": "room-1",
                "room_name": "Ocean View Deluxe Suite",
                "property_id": "prop-1",
                "check_in": "2026-02-18",
                "check_out": "2026-02-20",
                "status": "confirmed",
                "total_price": 578.0,
                "ai_handled": True,
                "source": "chatgpt",
                "conversation_id": "session-1",
            }
        ],
        "conversations": [
            {
                "id": "session-1",
                "guest_id": "guest-1",
                "channel": "widget",
                "started_at": "2026-02-17T09:30:00+00:00",
                "messages": [
                    {
                        "role": "guest",
                        "text": "Hi there",
                        "timestamp": "2026-02-17T09:30:00+00:00",
                    }
                ],
            }
        ],
    }


def test_list_guests_success_forwards_search_and_filters(monkeypatch):
    guest_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    guest_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(guest_routes, "user_owns_property", AsyncMock(return_value=True))
    list_mock = AsyncMock(
        return_value=[
            {
                "id": "guest-1",
                "property_id": "prop-1",
                "name": "Sarah Chen",
                "email": "sarah@example.com",
                "phone": "+1 415-555-0142",
                "notes": "",
                "total_stays": 1,
                "last_stay_date": "2026-02-20",
                "total_spent": 578.0,
                "latest_booking": None,
                "created_at": "2026-02-01T10:00:00+00:00",
                "updated_at": "2026-02-01T10:00:00+00:00",
            }
        ]
    )
    monkeypatch.setattr(guest_routes, "get_guests_by_property", list_mock)

    try:
        with TestClient(guest_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/guests",
                params={
                    "search": "sarah",
                    "room_id": "room-1",
                    "status": "confirmed",
                },
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["id"] == "guest-1"
        assert list_mock.await_args.kwargs["search"] == "sarah"
        assert list_mock.await_args.kwargs["room_id"] == "room-1"
        assert list_mock.await_args.kwargs["status"] == "confirmed"
    finally:
        guest_test_app.dependency_overrides = {}


def test_list_guests_success_forwards_combined_filters(monkeypatch):
    guest_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    guest_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(guest_routes, "user_owns_property", AsyncMock(return_value=True))
    list_mock = AsyncMock(
        return_value=[
            {
                "id": "guest-1",
                "property_id": "prop-1",
                "name": "Sarah Chen",
                "email": "sarah@example.com",
                "phone": "+1 415-555-0142",
                "notes": "",
                "total_stays": 1,
                "last_stay_date": "2026-02-20",
                "total_spent": 578.0,
                "latest_booking": None,
                "created_at": "2026-02-01T10:00:00+00:00",
                "updated_at": "2026-02-01T10:00:00+00:00",
            }
        ]
    )
    monkeypatch.setattr(guest_routes, "get_guests_by_property", list_mock)

    try:
        with TestClient(guest_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/guests",
                params={
                    "search": "vip",
                    "room_id": "room-2",
                    "status": "ai_pending",
                },
            )

        assert response.status_code == 200
        assert response.json()["items"][0]["id"] == "guest-1"
        assert list_mock.await_args.kwargs == {
            "search": "vip",
            "room_id": "room-2",
            "status": "ai_pending",
        }
    finally:
        guest_test_app.dependency_overrides = {}


def test_list_guests_access_denied(monkeypatch):
    guest_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    guest_test_app.dependency_overrides[get_supabase] = lambda: object()
    monkeypatch.setattr(guest_routes, "user_owns_property", AsyncMock(return_value=False))
    monkeypatch.setattr(guest_routes, "get_guests_by_property", AsyncMock(return_value=[]))

    try:
        with TestClient(guest_test_app) as client:
            response = client.get("/v1.0/properties/prop-1/guests")

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"
    finally:
        guest_test_app.dependency_overrides = {}


def test_get_guest_not_found(monkeypatch):
    guest_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    guest_test_app.dependency_overrides[get_supabase] = lambda: object()
    monkeypatch.setattr(guest_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(guest_routes, "get_guest_detail", AsyncMock(return_value=None))

    try:
        with TestClient(guest_test_app) as client:
            response = client.get("/v1.0/properties/prop-1/guests/guest-missing")

        assert response.status_code == 404
        assert response.json()["detail"] == "Guest not found"
    finally:
        guest_test_app.dependency_overrides = {}


def test_patch_guest_updates_and_returns_detail(monkeypatch):
    guest_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    guest_test_app.dependency_overrides[get_supabase] = lambda: object()
    monkeypatch.setattr(guest_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(
        guest_routes,
        "get_guest_by_id",
        AsyncMock(return_value={"id": "guest-1", "property_id": "prop-1"}),
    )
    update_mock = AsyncMock(return_value=_sample_guest_detail())
    monkeypatch.setattr(guest_routes, "update_guest", update_mock)

    try:
        with TestClient(guest_test_app) as client:
            response = client.patch(
                "/v1.0/properties/prop-1/guests/guest-1",
                json={"notes": " VIP ", "phone": " +1 415-555-0100 "},
            )

        assert response.status_code == 200
        assert response.json()["id"] == "guest-1"
        assert (
            response.json()["latest_booking"]["room_image"]
            == "https://cdn.example.com/room-1-main.jpg"
        )

        args = update_mock.await_args.args
        payload = args[3]
        assert payload["notes"] == "VIP"
        assert payload["phone"] == "+1 415-555-0100"
    finally:
        guest_test_app.dependency_overrides = {}


def test_extract_first_room_image_from_room_dict():
    booking = {
        "rooms": {
            "name": "Ocean View Deluxe Suite",
            "images": [
                "https://cdn.example.com/room-1-main.jpg",
                "https://cdn.example.com/room-1-secondary.jpg",
            ],
        }
    }

    assert _extract_first_room_image(booking) == "https://cdn.example.com/room-1-main.jpg"


def test_extract_first_room_image_from_room_list():
    booking = {
        "rooms": [
            {
                "name": "Ocean View Deluxe Suite",
                "images": ["https://cdn.example.com/room-1-main.jpg"],
            }
        ]
    }

    assert _extract_first_room_image(booking) == "https://cdn.example.com/room-1-main.jpg"


def test_extract_first_room_image_returns_none_when_missing_or_invalid():
    assert _extract_first_room_image({}) is None
    assert _extract_first_room_image({"rooms": {"images": []}}) is None
    assert _extract_first_room_image({"rooms": {"images": [123]}}) is None
    assert _extract_first_room_image({"rooms": {"images": ["  "]}}) is None


def test_map_latest_booking_sets_room_image_none_when_no_images():
    booking = {
        "id": "booking-1",
        "room_id": "room-1",
        "check_in": "2026-02-18",
        "check_out": "2026-02-20",
        "status": "confirmed",
        "total_price": 578.0,
        "ai_handled": True,
        "source": "gemini",
        "rooms": {"name": "Ocean View Deluxe Suite", "images": []},
    }

    mapped = _map_latest_booking(booking)
    assert mapped is not None
    assert mapped["room_image"] is None
    assert mapped["source"] == "gemini"
