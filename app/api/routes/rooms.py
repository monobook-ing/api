from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.crud.property import user_owns_property
from app.crud.room import (
    create_room,
    delete_room,
    get_room_by_id,
    get_rooms_by_property,
    update_room,
    upsert_room_pricing,
)
from app.db.base import get_supabase
from app.schemas.room import (
    RoomCreate,
    RoomImportRequest,
    RoomListResponse,
    RoomPricingUpdate,
    RoomResponse,
    RoomUpdate,
)
from app.services.airbnb_scraper import scrape_airbnb_listing, validate_airbnb_url
from app.services.booking_scraper import scrape_booking_listing, validate_booking_url

router = APIRouter(prefix="/v1.0/properties/{property_id}/rooms", tags=["rooms"])


async def _check_access(client: Client, user_id: str, property_id: str):
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _detect_listing_platform(url: str) -> str:
    trimmed = url.strip()
    with_scheme = trimmed if "://" in trimmed else f"https://{trimmed}"
    hostname = (urlparse(with_scheme).hostname or "").lower()
    if hostname.startswith("airbnb.") or ".airbnb." in hostname:
        return "airbnb"
    if hostname.startswith("booking.") or ".booking." in hostname:
        return "booking"
    raise ValueError(
        "Unsupported listing URL. Use an Airbnb or Booking.com listing URL."
    )


@router.get("", response_model=RoomListResponse)
async def list_rooms(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """List all rooms for a property."""
    await _check_access(client, current_user["id"], property_id)
    rooms = await get_rooms_by_property(client, property_id)
    return RoomListResponse(items=rooms)


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_new_room(
    property_id: str,
    payload: RoomCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Create a new room in a property."""
    await _check_access(client, current_user["id"], property_id)
    data = payload.model_dump()
    room = await create_room(client, property_id, data)
    return room


@router.post("/import", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def import_room_from_url(
    property_id: str,
    payload: RoomImportRequest,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Import a room from an Airbnb or Booking.com listing URL."""
    await _check_access(client, current_user["id"], property_id)

    try:
        platform = _detect_listing_platform(payload.url)
        canonical_url = (
            validate_airbnb_url(payload.url)
            if platform == "airbnb"
            else validate_booking_url(payload.url)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check for duplicate import
    existing = (
        client.table("rooms")
        .select("id")
        .eq("property_id", property_id)
        .eq("source_url", canonical_url)
        .execute()
    )
    if existing.data:
        source_label = "Airbnb" if platform == "airbnb" else "Booking.com"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This {source_label} listing has already been imported to this property.",
        )

    try:
        listing = (
            await scrape_airbnb_listing(payload.url)
            if platform == "airbnb"
            else await scrape_booking_listing(payload.url)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )

    room_data = {
        "name": listing.name,
        "type": listing.type,
        "description": listing.description,
        "images": listing.images,
        "price_per_night": listing.price_per_night,
        "currency_code": getattr(listing, "currency_code", "USD"),
        "max_guests": listing.max_guests,
        "bed_config": listing.bed_config,
        "amenities": listing.amenities,
        "source": platform,
        "source_url": canonical_url,
        "sync_enabled": False,
        "status": "active",
    }

    room = await create_room(client, property_id, room_data)
    return room


@router.get("/{room_id}", response_model=RoomResponse)
async def get_single_room(
    property_id: str,
    room_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get a single room with pricing details."""
    await _check_access(client, current_user["id"], property_id)
    room = await get_room_by_id(client, room_id)
    if not room or room["property_id"] != property_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


@router.patch("/{room_id}", response_model=RoomResponse)
async def update_existing_room(
    property_id: str,
    room_id: str,
    payload: RoomUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Update a room."""
    await _check_access(client, current_user["id"], property_id)
    room = await get_room_by_id(client, room_id)
    if not room or room["property_id"] != property_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    data = payload.model_dump(exclude_unset=True)
    updated = await update_room(client, room_id, data)
    return updated


@router.delete("/{room_id}", status_code=status.HTTP_200_OK)
async def delete_existing_room(
    property_id: str,
    room_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Delete a room."""
    await _check_access(client, current_user["id"], property_id)
    room = await get_room_by_id(client, room_id)
    if not room or room["property_id"] != property_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    await delete_room(client, room_id)
    return {"message": "Room deleted", "id": room_id}


@router.put("/{room_id}/pricing", response_model=RoomResponse)
async def set_room_pricing(
    property_id: str,
    room_id: str,
    payload: RoomPricingUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Replace all pricing (date overrides + guest tiers) for a room."""
    await _check_access(client, current_user["id"], property_id)
    room = await get_room_by_id(client, room_id)
    if not room or room["property_id"] != property_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    await upsert_room_pricing(
        client,
        room_id,
        [d.model_dump() for d in payload.date_overrides],
        [t.model_dump() for t in payload.guest_tiers],
    )
    return await get_room_by_id(client, room_id)
