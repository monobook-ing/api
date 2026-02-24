from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.crud.audit import get_audit_log
from app.db.base import get_supabase
import app.api.routes.audit as audit_routes

audit_test_app = FastAPI()
audit_test_app.include_router(audit_routes.router)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeAuditQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.filters: list = []
        self.limit_value: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(lambda row: row.get(field) == value)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def gte(self, field, value):
        self.filters.append(lambda row: row.get(field) >= value)
        return self

    def lte(self, field, value):
        self.filters.append(lambda row: row.get(field) <= value)
        return self

    def lt(self, field, value):
        self.filters.append(lambda row: row.get(field) < value)
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def execute(self):
        filtered = [row for row in self.rows if all(predicate(row) for predicate in self.filters)]
        filtered = sorted(filtered, key=lambda row: row["created_at"], reverse=True)
        if self.limit_value is not None:
            filtered = filtered[: self.limit_value]
        return FakeResponse(filtered)


class FakeSupabaseClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    def table(self, table_name: str):
        assert table_name == "audit_log"
        return FakeAuditQuery(self.rows)


def _override_current_user():
    return {"id": "user-1", "email": "user@example.com"}


def test_list_audit_log_forwards_from_to_filters(monkeypatch):
    audit_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    audit_test_app.dependency_overrides[get_supabase] = lambda: object()
    monkeypatch.setattr(audit_routes, "user_owns_property", AsyncMock(return_value=True))

    get_audit_log_mock = AsyncMock(return_value=([], None))
    monkeypatch.setattr(audit_routes, "get_audit_log", get_audit_log_mock)

    try:
        with TestClient(audit_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/audit",
                params={
                    "from": "2026-02-22T00:00:00+00:00",
                    "to": "2026-02-22T23:59:59+00:00",
                    "source": "mcp",
                },
            )

        assert response.status_code == 200
        args = get_audit_log_mock.await_args.args
        kwargs = get_audit_log_mock.await_args.kwargs
        assert args[1] == "prop-1"
        assert kwargs["source"] == "mcp"
        assert kwargs["from_dt"] == "2026-02-22T00:00:00+00:00"
        assert kwargs["to_dt"] == "2026-02-22T23:59:59+00:00"
    finally:
        audit_test_app.dependency_overrides = {}


def test_list_audit_log_rejects_invalid_from_datetime(monkeypatch):
    audit_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    audit_test_app.dependency_overrides[get_supabase] = lambda: object()
    monkeypatch.setattr(audit_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(audit_routes, "get_audit_log", AsyncMock(return_value=([], None)))

    try:
        with TestClient(audit_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/audit",
                params={"from": "not-a-date"},
            )

        assert response.status_code == 422
    finally:
        audit_test_app.dependency_overrides = {}


def test_list_audit_log_rejects_from_after_to(monkeypatch):
    audit_test_app.dependency_overrides[deps.get_current_user] = _override_current_user
    audit_test_app.dependency_overrides[get_supabase] = lambda: object()
    monkeypatch.setattr(audit_routes, "user_owns_property", AsyncMock(return_value=True))
    monkeypatch.setattr(audit_routes, "get_audit_log", AsyncMock(return_value=([], None)))

    try:
        with TestClient(audit_test_app) as client:
            response = client.get(
                "/v1.0/properties/prop-1/audit",
                params={
                    "from": "2026-02-23T00:00:00+00:00",
                    "to": "2026-02-22T23:59:59+00:00",
                },
            )

        assert response.status_code == 422
        assert response.json()["detail"] == "'from' must be less than or equal to 'to'"
    finally:
        audit_test_app.dependency_overrides = {}


def test_get_audit_log_applies_inclusive_date_filters():
    rows = [
        {
            "id": "audit-1",
            "property_id": "prop-1",
            "source": "mcp",
            "created_at": "2026-02-21T12:00:00+00:00",
        },
        {
            "id": "audit-2",
            "property_id": "prop-1",
            "source": "mcp",
            "created_at": "2026-02-22T14:00:00+00:00",
        },
        {
            "id": "audit-3",
            "property_id": "prop-1",
            "source": "mcp",
            "created_at": "2026-02-24T10:00:00+00:00",
        },
    ]
    client = FakeSupabaseClient(rows)

    items, next_cursor = _run_async(
        get_audit_log(
            client,
            "prop-1",
            source="mcp",
            from_dt="2026-02-22T00:00:00+00:00",
            to_dt="2026-02-22T23:59:59+00:00",
            limit=10,
        )
    )

    assert next_cursor is None
    assert [item["id"] for item in items] == ["audit-2"]


def test_get_audit_log_cursor_stays_within_date_range():
    rows = [
        {
            "id": "audit-1",
            "property_id": "prop-1",
            "source": "mcp",
            "created_at": "2026-02-24T10:00:00+00:00",
        },
        {
            "id": "audit-2",
            "property_id": "prop-1",
            "source": "mcp",
            "created_at": "2026-02-23T10:00:00+00:00",
        },
        {
            "id": "audit-3",
            "property_id": "prop-1",
            "source": "mcp",
            "created_at": "2026-02-22T10:00:00+00:00",
        },
    ]
    client = FakeSupabaseClient(rows)

    first_page, cursor = _run_async(
        get_audit_log(
            client,
            "prop-1",
            source="mcp",
            from_dt="2026-02-22T00:00:00+00:00",
            to_dt="2026-02-23T23:59:59+00:00",
            limit=1,
        )
    )
    second_page, second_cursor = _run_async(
        get_audit_log(
            client,
            "prop-1",
            source="mcp",
            from_dt="2026-02-22T00:00:00+00:00",
            to_dt="2026-02-23T23:59:59+00:00",
            limit=1,
            cursor=cursor,
        )
    )

    assert [item["id"] for item in first_page] == ["audit-2"]
    assert [item["id"] for item in second_page] == ["audit-3"]
    assert second_cursor is None


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)
