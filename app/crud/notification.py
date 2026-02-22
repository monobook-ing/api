import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime
from typing import Any

from supabase import Client

from app.schemas.notification import NotificationType


def _encode_cursor(created_at: str | datetime, notification_id: str) -> str:
    """Encode pagination cursor payload for notifications."""

    created_at_value = (
        created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
    )

    payload = {"created_at": created_at_value, "id": notification_id}
    raw = json.dumps(payload).encode("utf-8")
    return urlsafe_b64encode(raw).decode("utf-8")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a pagination cursor string.

    Raises:
        ValueError: If the cursor cannot be decoded or is missing expected
            fields.
    """

    try:
        raw = urlsafe_b64decode(cursor).decode("utf-8")
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 - intentional broad catch for decoding errors
        raise ValueError("Invalid pagination cursor") from exc

    if not isinstance(payload, dict) or not {"created_at", "id"}.issubset(payload):
        raise ValueError("Invalid pagination cursor")

    return payload


async def create_notification(
    client: Client,
    *,
    user_id: str,
    subject: str,
    body: str,
    notification_type: NotificationType | str = NotificationType.WELCOME,
    details: str | None = None,
    cta: str | None = None,
) -> dict:
    """Create a notification record for a user."""
    notification_data = {
        "user_id": user_id,
        "subject": subject,
        "body": body,
        "type": (
            notification_type.value
            if isinstance(notification_type, NotificationType)
            else notification_type
        ),
        "details": details,
        "cta": cta,
    }

    response = client.table("notifications").insert(notification_data).execute()

    if not response.data or len(response.data) == 0:
        raise ValueError("Failed to create notification")

    return response.data[0]


async def get_user_notification_by_subject(
    client: Client, *, user_id: str, subject: str
) -> dict | None:
    """Get a notification for a user that matches the given subject."""
    response = (
        client.table("notifications")
        .select("*")
        .eq("user_id", user_id)
        .eq("subject", subject)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def get_user_notifications(
    client: Client,
    user_id: str,
    *,
    is_read: bool | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    """Get notifications for a user ordered by newest first with pagination."""
    query = (
        client.table("notifications")
        .select("*")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
    )

    if is_read is not None:
        query = query.eq("is_read", is_read)

    if cursor:
        payload = _decode_cursor(cursor)
        created_at = str(payload["created_at"])
        notification_id = str(payload["id"])
        condition = (
            f"and(created_at.eq.{created_at},id.lt.{notification_id}),"
            f"created_at.lt.{created_at}"
        )
        query = query.or_(condition)

    query = query.order("created_at", desc=True).order("id", desc=True).limit(limit + 1)

    response = query.execute()
    notifications = response.data or []

    next_cursor = None
    if len(notifications) > limit:
        last_item = notifications[limit - 1]
        next_cursor = _encode_cursor(last_item["created_at"], last_item["id"])

    return {"items": notifications[:limit], "next_cursor": next_cursor}


async def get_user_notifications_count(
    client: Client, *, user_id: str, is_read: bool | None = None
) -> int:
    """Get the total number of notifications for a user with optional read filtering."""
    query = (
        client.table("notifications")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
    )

    if is_read is not None:
        query = query.eq("is_read", is_read)

    response = query.execute()
    return int(response.count or 0)


async def get_user_notification_by_id(
    client: Client, *, notification_id: str, user_id: str
) -> dict | None:
    """Get a specific notification for a user if it exists."""
    response = (
        client.table("notifications")
        .select("*")
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]
    return None


async def mark_all_notifications_as_read(client: Client, user_id: str) -> list[dict]:
    """Mark all non-deleted notifications for a user as read."""
    read_at = datetime.now(UTC).isoformat()
    response = (
        client.table("notifications")
        .update({"is_read": True, "read_at": read_at})
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )

    return response.data or []


async def mark_notification_as_read(client: Client, *, notification_id: str, user_id: str) -> dict:
    """Mark a single notification as read for a user."""
    read_at = datetime.now(UTC).isoformat()
    response = (
        client.table("notifications")
        .update({"is_read": True, "read_at": read_at})
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .is_("deleted_at", "null")
        .execute()
    )

    if not response.data:
        raise ValueError("Notification not found")

    return response.data[0]
