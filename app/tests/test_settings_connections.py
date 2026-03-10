from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
import app.api.routes.settings_connections as settings_routes
from app.crud import booking as booking_crud
from app.crud import settings as settings_crud
from app.db.base import get_supabase

settings_test_app = FastAPI()
settings_test_app.include_router(settings_routes.router)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.filters: list = []
        self.orders: list[tuple[str, bool]] = []
        self.limit_value: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(lambda row, field=field, value=value: row.get(field) == value)
        return self

    def gte(self, field, value):
        self.filters.append(lambda row, field=field, value=value: row.get(field) >= value)
        return self

    def lte(self, field, value):
        self.filters.append(lambda row, field=field, value=value: row.get(field) <= value)
        return self

    def order(self, field, desc: bool = False):
        self.orders.append((field, desc))
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def execute(self):
        filtered = [
            dict(row)
            for row in self.rows
            if all(predicate(row) for predicate in self.filters)
        ]
        for field, desc in reversed(self.orders):
            filtered = sorted(
                filtered,
                key=lambda row, field=field: row.get(field),
                reverse=desc,
            )
        if self.limit_value is not None:
            filtered = filtered[: self.limit_value]
        return FakeResponse(filtered)


class FakeSupabaseClient:
    def __init__(self, storage: dict[str, list[dict]]):
        self.storage = storage

    def table(self, table_name: str):
        return FakeTableQuery(self.storage.get(table_name, []))


def _override_current_user():
    return {"id": "user-1", "email": "user@example.com"}


def test_get_metrics_uses_default_year_range(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=True))
    metrics_mock = AsyncMock(
        return_value=[
            {
                "ai_direct_bookings": 10,
                "commission_saved": 1000,
                "occupancy_rate": 75,
                "revenue": 5000,
            },
            {
                "ai_direct_bookings": 15,
                "commission_saved": 1500,
                "occupancy_rate": 80,
                "revenue": 6500,
            },
        ]
    )
    monkeypatch.setattr(settings_routes, "get_dashboard_metrics", metrics_mock)

    try:
        with TestClient(settings_test_app) as client:
            response = client.get("/v1.0/properties/prop-1/metrics")

        assert response.status_code == 200
        assert response.json()["ai_direct_bookings"] == 15
        assert response.json()["ai_direct_bookings_trend"] == [10, 15]
        assert metrics_mock.await_args.kwargs["range_preset"] == "year"
        assert metrics_mock.await_args.kwargs["start_date"] is None
        assert metrics_mock.await_args.kwargs["end_date"] is None
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_metrics_forwards_explicit_ranges(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=True))
    metrics_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(settings_routes, "get_dashboard_metrics", metrics_mock)

    try:
        with TestClient(settings_test_app) as client:
            for preset in ("week", "month", "year"):
                metrics_mock.reset_mock()
                response = client.get(
                    "/v1.0/properties/prop-1/metrics",
                    params={"range": preset},
                )
                assert response.status_code == 200
                assert metrics_mock.await_args.kwargs["range_preset"] == preset
                assert metrics_mock.await_args.kwargs["start_date"] is None
                assert metrics_mock.await_args.kwargs["end_date"] is None

            metrics_mock.reset_mock()
            response = client.get(
                "/v1.0/properties/prop-1/metrics",
                params={
                    "range": "custom",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-28",
                },
            )
            assert response.status_code == 200
            assert metrics_mock.await_args.kwargs["range_preset"] == "custom"
            assert str(metrics_mock.await_args.kwargs["start_date"]) == "2026-02-01"
            assert str(metrics_mock.await_args.kwargs["end_date"]) == "2026-02-28"
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_metrics_rejects_custom_without_required_dates(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=True))
    metrics_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(settings_routes, "get_dashboard_metrics", metrics_mock)

    try:
        with TestClient(settings_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/metrics",
                params={"range": "custom", "start_date": "2026-02-01"},
            )

        assert response.status_code == 422
        assert response.json()["detail"] == "Custom range requires start_date and end_date"
        metrics_mock.assert_not_awaited()
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_metrics_rejects_custom_inverted_dates(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=True))
    metrics_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(settings_routes, "get_dashboard_metrics", metrics_mock)

    try:
        with TestClient(settings_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/metrics",
                params={
                    "range": "custom",
                    "start_date": "2026-02-10",
                    "end_date": "2026-02-01",
                },
            )

        assert response.status_code == 422
        assert response.json()["detail"] == "start_date cannot be after end_date"
        metrics_mock.assert_not_awaited()
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_metrics_access_denied(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=False))
    monkeypatch.setattr(settings_routes, "get_dashboard_metrics", AsyncMock(return_value=[]))

    try:
        with TestClient(settings_test_app) as client:
            response = client.get("/v1.0/properties/prop-1/metrics")

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_metrics_returns_default_shape_when_empty(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(settings_routes, "get_dashboard_metrics", AsyncMock(return_value=[]))

    try:
        with TestClient(settings_test_app) as client:
            response = client.get("/v1.0/properties/prop-1/metrics")

        assert response.status_code == 200
        assert response.json() == {
            "ai_direct_bookings": 0,
            "commission_saved": 0,
            "occupancy_rate": 0,
            "revenue": 0,
            "ai_direct_bookings_trend": [],
            "commission_saved_trend": [],
            "occupancy_trend": [],
            "revenue_trend": [],
        }
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_recent_activity_orders_with_limit(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=True))
    activity_mock = AsyncMock(
        return_value=[
            {
                "booking_id": "booking-2",
                "guest_name": "James Wilson",
                "check_in": "2026-03-22",
                "check_out": "2026-03-25",
                "ai_handled": True,
                "status": "confirmed",
                "created_at": "2026-02-22T12:15:45Z",
            },
            {
                "booking_id": "booking-1",
                "guest_name": "Sarah Chen",
                "check_in": "2026-03-15",
                "check_out": "2026-03-20",
                "ai_handled": True,
                "status": "confirmed",
                "created_at": "2026-02-22T11:33:12Z",
            },
        ]
    )
    monkeypatch.setattr(settings_routes, "get_recent_booking_activity", activity_mock)

    try:
        with TestClient(settings_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/recent-activity",
                params={"limit": 2},
            )

        assert response.status_code == 200
        assert [item["booking_id"] for item in response.json()["items"]] == [
            "booking-2",
            "booking-1",
        ]
        assert activity_mock.await_args.kwargs["limit"] == 2
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_recent_activity_access_denied(monkeypatch):
    settings_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    settings_test_app.dependency_overrides[get_supabase] = lambda: object()

    monkeypatch.setattr(settings_routes, "user_owns_property", AsyncMock(return_value=False))
    monkeypatch.setattr(
        settings_routes, "get_recent_booking_activity", AsyncMock(return_value=[])
    )

    try:
        with TestClient(settings_test_app) as client:
            response = client.get("/v1.0/properties/prop-1/recent-activity")

        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"
    finally:
        settings_test_app.dependency_overrides = {}


def test_get_dashboard_metrics_applies_date_windows(monkeypatch):
    storage = {
        "dashboard_metrics": [
            {
                "property_id": "prop-1",
                "date": "2026-03-09",
                "ai_direct_bookings": 12,
                "commission_saved": 1400,
                "occupancy_rate": 84,
                "revenue": 9700,
            },
            {
                "property_id": "prop-1",
                "date": "2026-03-05",
                "ai_direct_bookings": 11,
                "commission_saved": 1200,
                "occupancy_rate": 82,
                "revenue": 9300,
            },
            {
                "property_id": "prop-1",
                "date": "2026-01-20",
                "ai_direct_bookings": 9,
                "commission_saved": 980,
                "occupancy_rate": 78,
                "revenue": 8700,
            },
            {
                "property_id": "prop-1",
                "date": "2025-10-15",
                "ai_direct_bookings": 6,
                "commission_saved": 700,
                "occupancy_rate": 73,
                "revenue": 7600,
            },
            {
                "property_id": "prop-1",
                "date": "2024-12-01",
                "ai_direct_bookings": 4,
                "commission_saved": 400,
                "occupancy_rate": 68,
                "revenue": 6100,
            },
            {
                "property_id": "prop-2",
                "date": "2026-03-06",
                "ai_direct_bookings": 88,
                "commission_saved": 9100,
                "occupancy_rate": 95,
                "revenue": 45000,
            },
        ]
    }
    client = FakeSupabaseClient(storage)
    monkeypatch.setattr(settings_crud, "_utc_today", lambda: date(2026, 3, 10))

    week_rows = _run_async(
        settings_crud.get_dashboard_metrics(client, "prop-1", range_preset="week")
    )
    month_rows = _run_async(
        settings_crud.get_dashboard_metrics(client, "prop-1", range_preset="month")
    )
    year_rows = _run_async(
        settings_crud.get_dashboard_metrics(client, "prop-1", range_preset="year")
    )
    custom_rows = _run_async(
        settings_crud.get_dashboard_metrics(
            client,
            "prop-1",
            range_preset="custom",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 2, 28),
        )
    )

    assert [row["date"] for row in week_rows] == ["2026-03-05", "2026-03-09"]
    assert [row["date"] for row in month_rows] == ["2026-03-05", "2026-03-09"]
    assert [row["date"] for row in year_rows] == [
        "2025-10-15",
        "2026-01-20",
        "2026-03-05",
        "2026-03-09",
    ]
    assert [row["date"] for row in custom_rows] == ["2026-01-20"]


def test_get_recent_booking_activity_orders_by_created_at_then_id():
    storage = {
        "bookings": [
            {
                "id": "booking-001",
                "property_id": "prop-1",
                "check_in": "2026-03-15",
                "check_out": "2026-03-20",
                "status": "confirmed",
                "ai_handled": True,
                "created_at": "2026-02-22T10:00:00Z",
                "guests": {"name": "Sarah Chen"},
            },
            {
                "id": "booking-002",
                "property_id": "prop-1",
                "check_in": "2026-03-16",
                "check_out": "2026-03-21",
                "status": "pending",
                "ai_handled": False,
                "created_at": "2026-02-22T10:00:00Z",
                "guests": {"name": "James Wilson"},
            },
            {
                "id": "booking-003",
                "property_id": "prop-1",
                "check_in": "2026-03-18",
                "check_out": "2026-03-22",
                "status": "ai_pending",
                "ai_handled": True,
                "created_at": "2026-02-22T11:30:00Z",
                "guests": {"name": "Maria Garcia"},
            },
            {
                "id": "booking-999",
                "property_id": "prop-2",
                "check_in": "2026-03-10",
                "check_out": "2026-03-12",
                "status": "confirmed",
                "ai_handled": True,
                "created_at": "2026-02-23T11:30:00Z",
                "guests": {"name": "Other Property"},
            },
        ]
    }
    client = FakeSupabaseClient(storage)

    rows = _run_async(booking_crud.get_recent_booking_activity(client, "prop-1", limit=3))

    assert [row["booking_id"] for row in rows] == [
        "booking-003",
        "booking-002",
        "booking-001",
    ]
    assert [row["guest_name"] for row in rows] == [
        "Maria Garcia",
        "James Wilson",
        "Sarah Chen",
    ]


def _run_async(coro):
    return asyncio.run(coro)
