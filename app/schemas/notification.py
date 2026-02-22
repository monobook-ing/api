from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class NotificationType(str, Enum):
    """Supported notification types."""

    WELCOME = "welcome"
    NEWS = "news"
    UPDATES = "updates"
    INVITE_ACCEPTED = "invite_accepted"


class NotificationResponse(BaseModel):
    """Response schema for user notifications."""

    id: str
    user_id: str
    subject: str
    body: str
    type: NotificationType
    details: str | None = None
    cta: str | None = None
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Response schema for paginated notification results."""

    items: list[NotificationResponse]
    next_cursor: str | None


class NotificationCountResponse(BaseModel):
    """Response schema for notification count results."""

    count: int
