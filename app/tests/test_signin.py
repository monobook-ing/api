from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.api.routes.signin import confirm_magic_link, create_magic_link
from app.schemas.magic_link import MagicLinkConfirm, MagicLinkRequest


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

    def insert(self, data: dict):
        self.action = "insert"
        self.update_data = data
        return self

    def delete(self):
        self.action = "delete"
        return self

    def execute(self):
        rows = [
            row
            for row in self.storage.get(self.table_name, [])
            if all(f(row) for f in self.filters)
        ]

        if self.action == "select":
            if self.limit_value is not None:
                rows = rows[: self.limit_value]
            return FakeResponse(rows)

        if self.action == "update":
            updated_rows = []
            for row in self.storage.get(self.table_name, []):
                if all(f(row) for f in self.filters):
                    row.update(self.update_data)
                    updated_rows.append(row.copy())
            return FakeResponse(updated_rows)

        if self.action == "insert":
            new_rows = (
                self.update_data if isinstance(self.update_data, list) else [self.update_data]
            )
            self.storage.setdefault(self.table_name, []).extend(new_rows)
            return FakeResponse(new_rows)

        if self.action == "delete":
            remaining = []
            deleted = []
            for row in self.storage.get(self.table_name, []):
                if all(f(row) for f in self.filters):
                    deleted.append(row)
                else:
                    remaining.append(row)
            self.storage[self.table_name] = remaining
            return FakeResponse(deleted)

        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, storage: dict[str, list[dict]]):
        self.storage = storage

    def table(self, table_name: str):
        return FakeTableQuery(table_name, self.storage)


class CreateMagicLinkTests(IsolatedAsyncioTestCase):
    async def test_generates_and_persists_magic_link(self):
        fake_user = {"id": "user-1", "email": "user@example.com"}
        client = MagicMock()
        mock_get_user = AsyncMock(return_value=fake_user)
        mock_create_token = AsyncMock()
        mock_send_email = AsyncMock()

        token_value = "123e4567-e89b-12d3-a456-426614174000"

        with patch("app.api.routes.signin.get_user_by_email", mock_get_user), patch(
            "app.api.routes.signin.create_magic_token", mock_create_token
        ), patch("app.api.routes.signin.send_magic_link_email", mock_send_email), patch(
            "app.api.routes.signin.uuid4", return_value=UUID(token_value)
        ):
            payload = MagicLinkRequest(email="user@example.com")
            response = await create_magic_link(payload, client=client)

        self.assertEqual(response.token, token_value)
        self.assertIsNotNone(response.expires_at)
        self.assertGreater(response.expires_at, datetime.now(timezone.utc))

        mock_get_user.assert_awaited_once_with(client, payload.email)
        mock_create_token.assert_awaited_once()
        _, kwargs = mock_create_token.await_args
        self.assertEqual(kwargs["email"], payload.email)
        self.assertEqual(kwargs["token"], token_value)
        self.assertEqual(kwargs["user_id"], fake_user["id"])
        self.assertEqual(kwargs["expires_at"], response.expires_at)

        mock_send_email.assert_awaited_once_with(
            recipient=payload.email, token=token_value, expires_at=response.expires_at
        )


class ConfirmMagicLinkTests(IsolatedAsyncioTestCase):
    def setUp(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        self.magic_token = {
            "email": "user@example.com",
            "expires_at": future.isoformat(),
            "token": "tkn",
        }
        self.invitee = {"id": "user-1", "email": "user@example.com", "first_name": "User"}
        self.inviter = {
            "id": "inviter-1",
            "email": "inviter@example.com",
            "first_name": "Inviter",
            "last_name": "Person",
        }
        self.account = {"id": "acct-1", "name": "Demo Account"}
        self.settings = SimpleNamespace(
            app_name="fastapi-starter-kit",
            access_token_expire_minutes=30,
            jwt_secret="secret",
            algorithm="HS256",
        )

    def _client_with_memberships(self, membership_status: str):
        storage = {
            "users": [self.invitee, self.inviter],
            "team_members": [
                {
                    "id": "tm-1",
                    "user_id": self.invitee["id"],
                    "status": membership_status,
                    "account_id": self.account["id"],
                    "created_by": self.inviter["id"],
                    "deleted_at": None,
                }
            ],
            "accounts": [self.account],
        }
        return FakeSupabaseClient(storage), storage

    def _patch_common(self):
        self.create_notification = AsyncMock(return_value={})
        patches = [
            patch(
                "app.api.routes.signin.get_magic_token_by_token",
                AsyncMock(return_value=self.magic_token),
            ),
            patch("app.api.routes.signin.delete_magic_token", AsyncMock(return_value=True)),
            patch("app.api.routes.signin.get_user_by_email", AsyncMock(return_value=self.invitee)),
            patch(
                "app.api.routes.signin.get_user_notification_by_subject",
                AsyncMock(return_value={"id": "existing"}),
            ),
            patch(
                "app.api.routes.signin.create_notification",
                self.create_notification,
            ),
            patch("app.api.routes.signin.send_welcome_email", AsyncMock()),
            patch("app.api.routes.signin.get_settings", return_value=self.settings),
            patch("app.api.routes.signin.create_access_token", return_value="access-token"),
        ]
        for ctx in patches:
            ctx.start()
            self.addCleanup(ctx.stop)

    async def test_invite_acceptance_triggers_inviter_email(self):
        client, storage = self._client_with_memberships("invited")
        self._patch_common()

        send_invite_email = AsyncMock()
        patcher = patch("app.api.routes.signin.send_invite_accepted_email", send_invite_email)
        patcher.start()
        self.addCleanup(patcher.stop)

        response = await confirm_magic_link(
            MagicLinkConfirm(email="user@example.com", token="tkn"), client=client
        )

        self.assertEqual("accepted", response["user"]["team_member_status"])
        self.assertEqual("accepted", storage["team_members"][0]["status"])
        send_invite_email.assert_awaited_once()
        call_kwargs = send_invite_email.await_args.kwargs
        self.assertEqual(call_kwargs["recipient"], self.inviter["email"])
        self.assertEqual(call_kwargs["invitee_email"], self.invitee["email"])
        self.assertEqual(call_kwargs["account_name"], self.account["name"])
        self.create_notification.assert_awaited_once()

    async def test_no_invitation_skips_inviter_email(self):
        client, _ = self._client_with_memberships("accepted")
        self._patch_common()

        send_invite_email = AsyncMock()
        patcher = patch("app.api.routes.signin.send_invite_accepted_email", send_invite_email)
        patcher.start()
        self.addCleanup(patcher.stop)

        response = await confirm_magic_link(
            MagicLinkConfirm(email="user@example.com", token="tkn"), client=client
        )

        self.assertIsNone(response["user"]["team_member_status"])
        send_invite_email.assert_not_called()

    async def test_rejected_invitation_skips_inviter_email(self):
        client, _ = self._client_with_memberships("rejected")
        self._patch_common()

        send_invite_email = AsyncMock()
        patcher = patch("app.api.routes.signin.send_invite_accepted_email", send_invite_email)
        patcher.start()
        self.addCleanup(patcher.stop)

        response = await confirm_magic_link(
            MagicLinkConfirm(email="user@example.com", token="tkn"), client=client
        )

        self.assertEqual("rejected", response["user"]["team_member_status"])
        send_invite_email.assert_not_called()

    async def test_invited_member_signin_confirms_membership_and_returns_token(self):
        client, storage = self._client_with_memberships("invited")
        magic_token = {
            "email": "user@example.com",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "token": "tkn",
        }

        delete_magic_token = AsyncMock()
        send_invite_email = AsyncMock()

        with patch(
            "app.api.routes.signin.get_magic_token_by_token", AsyncMock(return_value=magic_token)
        ), patch("app.api.routes.signin.delete_magic_token", delete_magic_token), patch(
            "app.api.routes.signin.get_user_by_email", AsyncMock(return_value=self.invitee)
        ), patch(
            "app.api.routes.signin.get_user_notification_by_subject",
            AsyncMock(return_value={"id": "existing"}),
        ), patch("app.api.routes.signin.create_notification", AsyncMock()), patch(
            "app.api.routes.signin.send_welcome_email", AsyncMock()
        ), patch(
            "app.api.routes.signin.get_settings", return_value=self.settings
        ), patch(
            "app.api.routes.signin.create_access_token", return_value="jwt-token"
        ), patch(
            "app.api.routes.signin.send_invite_accepted_email", send_invite_email
        ):
            response = await confirm_magic_link(
                MagicLinkConfirm(email="user@example.com", token="tkn"), client=client
            )

        self.assertEqual("jwt-token", response["access_token"])
        self.assertEqual("bearer", response["token_type"])
        self.assertEqual("accepted", response["user"]["team_member_status"])
        self.assertEqual("accepted", storage["team_members"][0]["status"])

        delete_magic_token.assert_awaited_once_with(client, "tkn")
        send_invite_email.assert_awaited_once()
