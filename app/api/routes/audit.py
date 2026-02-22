from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.crud.audit import get_audit_log
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.audit import AuditLogListResponse

router = APIRouter(prefix="/v1.0/properties/{property_id}/audit", tags=["audit"])

ALLOWED_AUDIT_SOURCES = {"mcp", "chatgpt", "claude", "gemini", "widget"}


@router.get("", response_model=AuditLogListResponse)
async def list_audit_log(
    property_id: str,
    source: str | None = Query(None, description="Filter by source: mcp, chatgpt, claude, gemini, widget"),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get audit log entries for a property."""
    normalized_source = source.strip().lower() if source else None
    if normalized_source and normalized_source not in ALLOWED_AUDIT_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid source filter. Allowed values: "
                + ", ".join(sorted(ALLOWED_AUDIT_SOURCES))
            ),
        )

    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    rows, next_cursor = await get_audit_log(
        client,
        property_id,
        source=normalized_source,
        limit=limit,
        cursor=cursor,
    )
    return AuditLogListResponse(items=rows, next_cursor=next_cursor)
