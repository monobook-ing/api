from __future__ import annotations

import logging
from typing import Any

from supabase import Client

from app.crud.notification import create_notification
from app.schemas.notification import NotificationType

logger = logging.getLogger(__name__)


async def _get_property_recipient_user_ids(client: Client, property_id: str) -> list[str]:
    property_response = (
        client.table("properties")
        .select("account_id")
        .eq("id", property_id)
        .limit(1)
        .execute()
    )
    if not property_response.data:
        return []

    account_id = property_response.data[0].get("account_id")
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
    return user_ids


async def _get_room_name(client: Client, *, property_id: str, room_id: str | None) -> str:
    if not room_id:
        return "Room"

    query = client.table("rooms").select("name").eq("id", room_id)
    if property_id:
        query = query.eq("property_id", property_id)
    response = query.limit(1).execute()
    if not response.data:
        return "Room"

    room_name = response.data[0].get("name")
    return str(room_name).strip() if room_name else "Room"


def _build_booking_notification_content(
    booking: dict[str, Any],
    *,
    guest_name: str | None,
    room_name: str,
) -> tuple[str, str]:
    status = str(booking.get("status") or "").lower()
    subject = "New confirmed booking" if status == "confirmed" else "New booking created"

    guest_value = (guest_name or "").strip() or "Guest"
    check_in = booking.get("check_in") or "-"
    check_out = booking.get("check_out") or "-"
    currency_display = str(booking.get("currency_display") or "")
    total_price = booking.get("total_price")
    total_value = f"{currency_display}{total_price}" if currency_display else f"{total_price}"

    body = (
        f"Guest: {guest_value}. "
        f"Room: {room_name}. "
        f"Dates: {check_in} to {check_out}. "
        f"Total: {total_value}."
    )

    return subject, body


async def notify_booking_success(
    client: Client, *, booking: dict[str, Any], guest_name: str | None
) -> None:
    """Create best-effort booking success notifications for accepted team members."""
    try:
        property_id = str(booking.get("property_id") or "")
        if not property_id:
            return

        recipient_user_ids = await _get_property_recipient_user_ids(client, property_id)
        if not recipient_user_ids:
            return

        room_name = await _get_room_name(
            client,
            property_id=property_id,
            room_id=booking.get("room_id"),
        )
        subject, body = _build_booking_notification_content(
            booking,
            guest_name=guest_name,
            room_name=room_name,
        )

        for user_id in recipient_user_ids:
            try:
                await create_notification(
                    client,
                    user_id=user_id,
                    subject=subject,
                    body=body,
                    notification_type=NotificationType.BOOKING_SUCCESS,
                    details=body,
                    cta=None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to create booking success notification for user %s: %s",
                    user_id,
                    exc,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to process booking success notifications: %s", exc)
