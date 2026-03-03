from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents import tools
from app.api.routes.bookings import create_new_booking
from app.schemas.booking import BookingCreate


class FakeRoomQuery:
    def __init__(self, room_data: dict):
        self.room_data = room_data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=self.room_data)


class FakeToolClient:
    def __init__(self, room_data: dict):
        self.room_data = room_data

    def table(self, table_name: str):
        if table_name != "rooms":
            raise AssertionError(f"Unexpected table queried: {table_name}")
        return FakeRoomQuery(self.room_data)


class BookingNotificationWiringTests(IsolatedAsyncioTestCase):
    async def test_create_new_booking_emits_notification_after_success(self):
        payload = BookingCreate(
            room_id="room-1",
            guest_name="John Doe",
            guest_email="john@example.com",
            guest_phone=None,
            check_in=date(2026, 4, 10),
            check_out=date(2026, 4, 15),
            total_price=1445,
            currency_code="USD",
            status="confirmed",
            ai_handled=False,
            source="manual",
            conversation_id=None,
        )
        booking_row = {
            "id": "booking-1",
            "property_id": "prop-1",
            "room_id": "room-1",
            "currency_display": "$",
            "check_in": "2026-04-10",
            "check_out": "2026-04-15",
            "total_price": 1445,
            "status": "confirmed",
        }

        client = MagicMock()

        with patch("app.api.routes.bookings._check_access", AsyncMock()), patch(
            "app.api.routes.bookings.get_or_create_guest",
            AsyncMock(return_value="guest-1"),
        ), patch(
            "app.api.routes.bookings.create_booking",
            AsyncMock(return_value=booking_row),
        ), patch(
            "app.api.routes.bookings.link_session_to_guest",
            AsyncMock(),
        ), patch(
            "app.api.routes.bookings.notify_booking_success",
            AsyncMock(),
        ) as notify_booking_success:
            result = await create_new_booking(
                property_id="prop-1",
                payload=payload,
                current_user={"id": "user-1"},
                client=client,
            )

        self.assertEqual(result["id"], "booking-1")
        notify_booking_success.assert_awaited_once_with(
            client,
            booking=result,
            guest_name="John Doe",
        )

    async def test_create_new_booking_does_not_notify_when_creation_fails(self):
        payload = BookingCreate(
            room_id="room-1",
            guest_name="John Doe",
            guest_email="john@example.com",
            guest_phone=None,
            check_in=date(2026, 4, 10),
            check_out=date(2026, 4, 15),
            total_price=1445,
            currency_code="USD",
            status="confirmed",
            ai_handled=False,
            source="manual",
            conversation_id=None,
        )
        client = MagicMock()

        with patch("app.api.routes.bookings._check_access", AsyncMock()), patch(
            "app.api.routes.bookings.get_or_create_guest",
            AsyncMock(return_value="guest-1"),
        ), patch(
            "app.api.routes.bookings.create_booking",
            AsyncMock(side_effect=RuntimeError("insert failed")),
        ), patch(
            "app.api.routes.bookings.notify_booking_success",
            AsyncMock(),
        ) as notify_booking_success:
            with self.assertRaises(RuntimeError):
                await create_new_booking(
                    property_id="prop-1",
                    payload=payload,
                    current_user={"id": "user-1"},
                    client=client,
                )

        notify_booking_success.assert_not_awaited()

    async def test_tool_create_booking_emits_notification_on_success(self):
        client = FakeToolClient(
            {
                "name": "Ocean Suite",
                "type": "suite",
                "description": "Nice room",
                "images": [],
                "amenities": [],
                "max_guests": 4,
                "bed_config": "King",
            }
        )
        booking_row = {
            "id": "booking-1",
            "property_id": "prop-1",
            "room_id": "room-1",
            "check_in": "2026-04-10",
            "check_out": "2026-04-15",
            "total_price": 1445,
            "currency_display": "$",
            "status": "ai_pending",
        }

        with patch("app.agents.tools.validate_dates", return_value=None), patch(
            "app.agents.tools.validate_guests",
            return_value=None,
        ), patch(
            "app.agents.tools.check_availability",
            AsyncMock(return_value={"available": True}),
        ), patch(
            "app.agents.tools.calculate_price",
            AsyncMock(
                return_value={
                    "room_name": "Ocean Suite",
                    "nights": 5,
                    "nightly_rate": 220,
                    "subtotal": 1100,
                    "taxes": 165,
                    "service_fee": 44,
                    "total": 1309,
                    "currency": "USD",
                    "currency_code": "USD",
                    "currency_display": "$",
                }
            ),
        ), patch(
            "app.agents.tools.get_property_by_id",
            AsyncMock(return_value={"name": "Demo Hotel"}),
        ), patch(
            "app.agents.tools.get_or_create_guest",
            AsyncMock(return_value="guest-1"),
        ), patch(
            "app.agents.tools.create_booking",
            AsyncMock(return_value=booking_row),
        ), patch(
            "app.agents.tools.log_tool_call",
            AsyncMock(),
        ), patch(
            "app.agents.tools.notify_booking_success",
            AsyncMock(),
        ) as notify_booking_success:
            result = await tools.tool_create_booking(
                client=client,
                property_id="prop-1",
                room_id="room-1",
                guest_name="John Doe",
                guest_email="john@example.com",
                check_in="2026-04-10",
                check_out="2026-04-15",
                guests=2,
                session_id=None,
                source="widget",
                booking_status="ai_pending",
            )

        self.assertIn("booking_id", result)
        notify_booking_success.assert_awaited_once_with(
            client,
            booking=booking_row,
            guest_name="John Doe",
        )

    async def test_tool_create_booking_does_not_notify_when_unavailable(self):
        client = FakeToolClient(
            {
                "name": "Ocean Suite",
                "type": "suite",
                "description": "Nice room",
                "images": [],
                "amenities": [],
                "max_guests": 4,
                "bed_config": "King",
            }
        )

        with patch("app.agents.tools.validate_dates", return_value=None), patch(
            "app.agents.tools.validate_guests",
            return_value=None,
        ), patch(
            "app.agents.tools.check_availability",
            AsyncMock(return_value={"available": False}),
        ), patch(
            "app.agents.tools.notify_booking_success",
            AsyncMock(),
        ) as notify_booking_success:
            result = await tools.tool_create_booking(
                client=client,
                property_id="prop-1",
                room_id="room-1",
                guest_name="John Doe",
                guest_email="john@example.com",
                check_in="2026-04-10",
                check_out="2026-04-15",
                guests=2,
                session_id=None,
                source="widget",
                booking_status="ai_pending",
            )

        self.assertEqual(result.get("error"), "Room is not available for the selected dates.")
        notify_booking_success.assert_not_awaited()
