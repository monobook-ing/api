from __future__ import annotations

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.booking_notifications import notify_booking_success


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name: str, storage: dict[str, list[dict]]):
        self.table_name = table_name
        self.storage = storage
        self.filters: list = []
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

    def execute(self):
        rows = [
            row
            for row in self.storage.get(self.table_name, [])
            if all(predicate(row) for predicate in self.filters)
        ]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return FakeResponse(rows)


class FakeSupabaseClient:
    def __init__(self, storage: dict[str, list[dict]]):
        self.storage = storage

    def table(self, table_name: str):
        return FakeTableQuery(table_name, self.storage)


class BookingNotificationServiceTests(IsolatedAsyncioTestCase):
    async def test_notifies_only_accepted_non_deleted_team_members(self):
        storage = {
            "properties": [{"id": "prop-1", "account_id": "acct-1"}],
            "team_members": [
                {"account_id": "acct-1", "user_id": "user-1", "status": "accepted", "deleted_at": None},
                {"account_id": "acct-1", "user_id": "user-2", "status": "accepted", "deleted_at": None},
                {"account_id": "acct-1", "user_id": "user-3", "status": "invited", "deleted_at": None},
                {"account_id": "acct-1", "user_id": "user-4", "status": "rejected", "deleted_at": None},
                {
                    "account_id": "acct-1",
                    "user_id": "user-5",
                    "status": "accepted",
                    "deleted_at": "2026-03-03T00:00:00Z",
                },
            ],
            "rooms": [{"id": "room-1", "property_id": "prop-1", "name": "Ocean Suite"}],
        }
        client = FakeSupabaseClient(storage)

        booking = {
            "property_id": "prop-1",
            "room_id": "room-1",
            "check_in": "2026-04-10",
            "check_out": "2026-04-15",
            "total_price": 1445,
            "currency_display": "$",
            "status": "confirmed",
        }

        create_notification = AsyncMock()
        with patch(
            "app.services.booking_notifications.create_notification",
            create_notification,
        ):
            await notify_booking_success(client, booking=booking, guest_name="John Doe")

        self.assertEqual(create_notification.await_count, 2)
        user_ids = {call.kwargs["user_id"] for call in create_notification.await_args_list}
        self.assertEqual(user_ids, {"user-1", "user-2"})
        for call in create_notification.await_args_list:
            self.assertEqual(call.kwargs["subject"], "New confirmed booking")
            self.assertEqual(call.kwargs["notification_type"].value, "booking_success")
            self.assertEqual(
                call.kwargs["body"],
                "Guest: John Doe. Room: Ocean Suite. Dates: 2026-04-10 to 2026-04-15. Total: $1445.",
            )

    async def test_pending_booking_uses_generic_subject(self):
        storage = {
            "properties": [{"id": "prop-1", "account_id": "acct-1"}],
            "team_members": [
                {"account_id": "acct-1", "user_id": "user-1", "status": "accepted", "deleted_at": None}
            ],
            "rooms": [{"id": "room-1", "property_id": "prop-1", "name": "Sky Loft"}],
        }
        client = FakeSupabaseClient(storage)

        create_notification = AsyncMock()
        with patch(
            "app.services.booking_notifications.create_notification",
            create_notification,
        ):
            await notify_booking_success(
                client,
                booking={
                    "property_id": "prop-1",
                    "room_id": "room-1",
                    "check_in": "2026-05-01",
                    "check_out": "2026-05-05",
                    "total_price": 980,
                    "currency_display": "€",
                    "status": "pending",
                },
                guest_name="Alex",
            )

        self.assertEqual(create_notification.await_count, 1)
        self.assertEqual(
            create_notification.await_args.kwargs["subject"],
            "New booking created",
        )

    async def test_notification_creation_errors_do_not_raise(self):
        storage = {
            "properties": [{"id": "prop-1", "account_id": "acct-1"}],
            "team_members": [
                {"account_id": "acct-1", "user_id": "user-1", "status": "accepted", "deleted_at": None}
            ],
            "rooms": [{"id": "room-1", "property_id": "prop-1", "name": "Room"}],
        }
        client = FakeSupabaseClient(storage)

        with patch(
            "app.services.booking_notifications.create_notification",
            AsyncMock(side_effect=RuntimeError("write failed")),
        ):
            await notify_booking_success(
                client,
                booking={
                    "property_id": "prop-1",
                    "room_id": "room-1",
                    "check_in": "2026-05-01",
                    "check_out": "2026-05-05",
                    "total_price": 980,
                    "currency_display": "$",
                    "status": "confirmed",
                },
                guest_name="Alex",
            )
