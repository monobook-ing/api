from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.crud.notification import (
    get_user_notification_by_id,
    get_user_notifications,
    get_user_notifications_count,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)
from app.db.base import get_supabase
from app.schemas.notification import (
    NotificationCountResponse,
    NotificationListResponse,
    NotificationResponse,
)

router = APIRouter(prefix="/v1.0/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    is_read: bool | None = Query(None, description="Filter by read status"),
    limit: int = Query(20, ge=1, le=100, description="Number of results to return"),
    cursor: str
    | None = Query(None, description="Pagination cursor for infinite scroll behavior"),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> NotificationListResponse:
    """List notifications for the current user."""
    try:
        result = await get_user_notifications(
            client,
            current_user["id"],
            is_read=is_read,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return NotificationListResponse(
        items=[NotificationResponse(**notification) for notification in result["items"]],
        next_cursor=result["next_cursor"],
    )


@router.get("/count", response_model=NotificationCountResponse)
async def get_notifications_count(
    is_read: bool | None = Query(None, description="Filter by read status"),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> NotificationCountResponse:
    """Get the count of notifications for the current user."""
    count = await get_user_notifications_count(
        client, user_id=current_user["id"], is_read=is_read
    )
    return NotificationCountResponse(count=count)


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> NotificationResponse:
    """Retrieve a single notification for the current user."""
    notification = await get_user_notification_by_id(
        client, notification_id=notification_id, user_id=current_user["id"]
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return NotificationResponse(**notification)


@router.post("/read", response_model=list[NotificationResponse])
async def mark_all_notifications_read(
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> list[NotificationResponse]:
    """Mark all notifications for the current user as read."""
    notifications = await mark_all_notifications_as_read(client, current_user["id"])
    return [NotificationResponse(**notification) for notification in notifications]


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_single_notification_read(
    notification_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
) -> NotificationResponse:
    """Mark a single notification as read for the current user."""
    existing = await get_user_notification_by_id(
        client, notification_id=notification_id, user_id=current_user["id"]
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    updated = await mark_notification_as_read(
        client, notification_id=notification_id, user_id=current_user["id"]
    )
    return NotificationResponse(**updated)
