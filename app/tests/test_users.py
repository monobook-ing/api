from fastapi.testclient import TestClient

from app.api import deps
from app.db.base import get_supabase
from app.main import app


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name: str, storage: dict[str, list[dict]]):
        self.table_name = table_name
        self.storage = storage
        self.filters: list = []
        self.action = "select"
        self.update_data = None
        self.limit_value: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self.filters.append(lambda row: row.get(field) == value)
        return self

    def is_(self, field, value):
        if value == "null":
            self.filters.append(lambda row: row.get(field) is None)
        else:
            self.filters.append(lambda row: row.get(field) == value)
        return self

    def limit(self, count: int):
        self.limit_value = count
        return self

    def update(self, data: dict):
        self.action = "update"
        self.update_data = data
        return self

    def execute(self):
        rows = [
            row
            for row in self.storage.get(self.table_name, [])
            if all(f(row) for f in self.filters)
        ]

        if self.action == "update":
            updated_rows = []
            for row in self.storage.get(self.table_name, []):
                if all(f(row) for f in self.filters):
                    row.update(self.update_data)
                    updated_rows.append(row.copy())
            return FakeResponse(updated_rows)

        if self.action == "select":
            if self.limit_value is not None:
                rows = rows[: self.limit_value]
            return FakeResponse(rows)

        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, storage: dict[str, list[dict]]):
        self.storage = storage

    def table(self, table_name: str):
        return FakeTableQuery(table_name, self.storage)


def _override_current_user():
    return {"id": "user-1", "email": "user@example.com"}


def _get_fake_supabase():
    storage = {
        "users": [
            {
                "id": "user-1",
                "email": "user@example.com",
                "first_name": "Existing",
                "last_name": "User",
            }
        ],
        "accounts": [
            {
                "id": "acct-1",
                "created_by": "user-1",
                "is_default": True,
            }
        ],
        "team_members": [],
    }
    return FakeSupabaseClient(storage), storage


def test_update_current_user_success():
    supabase_client, storage = _get_fake_supabase()
    app.dependency_overrides[get_supabase] = lambda: supabase_client
    app.dependency_overrides[deps.get_current_user] = _override_current_user

    try:
        with TestClient(app) as client:
            response = client.patch(
                "/v1.0/users/me", json={"first_name": "Jane", "last_name": "Doe"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["first_name"] == "Jane"
        assert body["last_name"] == "Doe"
        assert body["default_account_id"] == "acct-1"
        assert storage["users"][0]["first_name"] == "Jane"
        assert storage["users"][0]["last_name"] == "Doe"
    finally:
        app.dependency_overrides = {}


def test_update_current_user_requires_auth():
    supabase_client, _ = _get_fake_supabase()
    app.dependency_overrides[get_supabase] = lambda: supabase_client

    try:
        with TestClient(app) as client:
            response = client.patch("/v1.0/users/me", json={"first_name": "Jane"})

        assert response.status_code == 401
    finally:
        app.dependency_overrides = {}


def test_update_current_user_validation_error():
    supabase_client, _ = _get_fake_supabase()
    app.dependency_overrides[get_supabase] = lambda: supabase_client
    app.dependency_overrides[deps.get_current_user] = _override_current_user

    try:
        with TestClient(app) as client:
            response = client.patch("/v1.0/users/me", json={"first_name": "   "})

        assert response.status_code == 422
    finally:
        app.dependency_overrides = {}
