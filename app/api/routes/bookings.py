from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.crud.booking import (
    create_booking,
    get_booking_by_id,
    get_bookings_by_property,
    get_or_create_guest,
    update_booking,
)
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.booking import (
    BookingCreate,
    BookingListResponse,
    BookingResponse,
    BookingUpdate,
)

router = APIRouter(prefix="/v1.0/properties/{property_id}/bookings", tags=["bookings"])


async def _check_access(client: Client, user_id: str, property_id: str):
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.get("", response_model=BookingListResponse)
async def list_bookings(
    property_id: str,
    status_filter: str | None = Query(None, alias="status"),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """List bookings for a property, optionally filtered by status."""
    await _check_access(client, current_user["id"], property_id)
    rows = await get_bookings_by_property(client, property_id, status=status_filter)
    return BookingListResponse(items=rows)


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_new_booking(
    property_id: str,
    payload: BookingCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Create a new booking."""
    await _check_access(client, current_user["id"], property_id)

    guest_id = await get_or_create_guest(
        client, property_id, payload.guest_name, payload.guest_email, payload.guest_phone
    )

    data = {
        "property_id": property_id,
        "room_id": payload.room_id,
        "guest_id": guest_id,
        "check_in": payload.check_in.isoformat(),
        "check_out": payload.check_out.isoformat(),
        "total_price": payload.total_price,
        "status": payload.status,
        "ai_handled": payload.ai_handled,
        "source": payload.source,
        "conversation_id": payload.conversation_id,
    }
    booking = await create_booking(client, data)
    booking["guest_name"] = payload.guest_name
    return booking


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_single_booking(
    property_id: str,
    booking_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get a single booking."""
    await _check_access(client, current_user["id"], property_id)
    booking = await get_booking_by_id(client, booking_id)
    if not booking or booking["property_id"] != property_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking


@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_existing_booking(
    property_id: str,
    booking_id: str,
    payload: BookingUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Update a booking (status, dates, price)."""
    await _check_access(client, current_user["id"], property_id)
    booking = await get_booking_by_id(client, booking_id)
    if not booking or booking["property_id"] != property_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    data = payload.model_dump(exclude_unset=True)
    if "check_in" in data and data["check_in"]:
        data["check_in"] = data["check_in"].isoformat()
    if "check_out" in data and data["check_out"]:
        data["check_out"] = data["check_out"].isoformat()
    updated = await update_booking(client, booking_id, data)
    return updated
