from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.api import deps
from app.core.config import get_settings
from app.crud.curated_place import (
    create_curated_place,
    delete_curated_place,
    get_curated_place,
    list_curated_places,
    update_curated_place,
)
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.curated_place import (
    CuratedPlaceCreate,
    CuratedPlaceImport,
    CuratedPlaceListResponse,
    CuratedPlaceResponse,
    CuratedPlaceUpdate,
)
from app.services.places import PlacesService

router = APIRouter(
    prefix="/v1.0/properties/{property_id}/curated-places",
    tags=["curated_places"],
)

settings = get_settings()


async def _check_access(client: Client, user_id: str, property_id: str) -> None:
    if not await user_owns_property(client, user_id, property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _assert_quality_gate(rating: float | None, review_count: int | None, *, force: bool) -> None:
    if force:
        return
    if rating is None or rating < 4.6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Place did not pass quality gate: rating must be at least 4.6.",
        )
    if review_count is None or review_count < 150:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Place did not pass quality gate: review_count must be at least 150.",
        )


@router.get("", response_model=CuratedPlaceListResponse)
async def list_property_curated_places(
    property_id: str,
    meal_type: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)
    items = await list_curated_places(client, property_id, meal_type=meal_type, tags=tags)
    return CuratedPlaceListResponse(items=items)


@router.post("", response_model=CuratedPlaceResponse, status_code=status.HTTP_201_CREATED)
async def create_property_curated_place(
    property_id: str,
    payload: CuratedPlaceCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)

    _assert_quality_gate(payload.rating, payload.review_count, force=False)

    created = await create_curated_place(
        client,
        property_id,
        payload.model_dump(),
    )
    return created


@router.get("/{place_id}", response_model=CuratedPlaceResponse)
async def get_property_curated_place(
    property_id: str,
    place_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)

    place = await get_curated_place(client, property_id, place_id)
    if not place:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Curated place not found")
    return place


@router.patch("/{place_id}", response_model=CuratedPlaceResponse)
async def patch_property_curated_place(
    property_id: str,
    place_id: str,
    payload: CuratedPlaceUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)

    existing = await get_curated_place(client, property_id, place_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Curated place not found")

    updated = await update_curated_place(
        client,
        property_id,
        place_id,
        payload.model_dump(exclude_unset=True),
    )
    return updated


@router.delete("/{place_id}", status_code=status.HTTP_200_OK)
async def remove_property_curated_place(
    property_id: str,
    place_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)

    existing = await get_curated_place(client, property_id, place_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Curated place not found")

    deleted = await delete_curated_place(client, property_id, place_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not delete place")

    return {"message": "Curated place deleted", "id": place_id}


@router.post("/import", response_model=CuratedPlaceResponse, status_code=status.HTTP_201_CREATED)
async def import_curated_place(
    property_id: str,
    payload: CuratedPlaceImport,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    await _check_access(client, current_user["id"], property_id)

    existing = (
        client.table("curated_places")
        .select("id")
        .eq("property_id", property_id)
        .eq("google_place_id", payload.google_place_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Google place is already imported for the property.",
        )

    api_key = settings.google_places_api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API key is not configured.",
        )

    details = await PlacesService.get_place_details(client, payload.google_place_id, api_key)
    if not details or not details.get("name"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not fetch Google place details for the provided place ID.",
        )

    _assert_quality_gate(
        details.get("rating"),
        details.get("review_count"),
        force=payload.force,
    )

    create_payload = {
        "google_place_id": details.get("place_id") or payload.google_place_id,
        "name": details.get("name"),
        "address": details.get("address"),
        "lat": details.get("lat"),
        "lng": details.get("lng"),
        "cuisine": details.get("cuisine") or [],
        "price_level": details.get("price_level"),
        "rating": details.get("rating"),
        "review_count": details.get("review_count"),
        "phone": details.get("phone"),
        "website": details.get("website"),
        "photo_urls": [details["photo_url"]] if details.get("photo_url") else [],
        "opening_hours": details.get("opening_hours"),
        "meal_types": details.get("meal_types") or [],
        "tags": details.get("best_for") or [],
        "best_for": details.get("best_for") or [],
    }

    created = await create_curated_place(client, property_id, create_payload)
    return created
