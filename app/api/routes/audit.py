from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.crud.audit import get_audit_log
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.audit import AuditLogListResponse

router = APIRouter(prefix="/v1.0/properties/{property_id}/audit", tags=["audit"])


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
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    rows, next_cursor = await get_audit_log(client, property_id, source=source, limit=limit, cursor=cursor)
    return AuditLogListResponse(items=rows, next_cursor=next_cursor)
