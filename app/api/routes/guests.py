from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.crud.guest import (
    get_guest_detail,
    get_guest_by_id,
    get_guests_by_property,
    update_guest,
)
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.guest import GuestDetailResponse, GuestListResponse, GuestUpdate

router = APIRouter(prefix="/v1.0/properties/{property_id}/guests", tags=["guests"])


async def _check_access(client: Client, user_id: str, property_id: str) -> None:
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("", response_model=GuestListResponse)
async def list_guests(
    property_id: str,
    search: str | None = Query(None, min_length=1, max_length=200),
    room_id: str | None = Query(None, min_length=1, max_length=200),
    status_filter: Literal["confirmed", "ai_pending"] | None = Query(
        None,
        alias="status",
    ),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    guests = await get_guests_by_property(
        client,
        property_id,
        search=search,
        room_id=room_id,
        status=status_filter,
    )
    return GuestListResponse(items=guests)


@router.get("/{guest_id}", response_model=GuestDetailResponse)
async def get_guest(
    property_id: str,
    guest_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    guest = await get_guest_detail(client, property_id, guest_id)
    if not guest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    return guest


@router.patch("/{guest_id}", response_model=GuestDetailResponse)
async def patch_guest(
    property_id: str,
    guest_id: str,
    payload: GuestUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)

    existing_guest = await get_guest_by_id(client, property_id, guest_id)
    if not existing_guest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")

    updated = await update_guest(
        client,
        property_id,
        guest_id,
        payload.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest not found")
    return updated
