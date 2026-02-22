from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.crud.property import (
    create_property,
    delete_property,
    get_properties_by_user,
    get_property_by_id,
    update_property,
    user_owns_property,
)
from app.db.base import get_supabase
from app.schemas.property import (
    PropertyCreate,
    PropertyListResponse,
    PropertyResponse,
    PropertyUpdate,
)

router = APIRouter(prefix="/v1.0/properties", tags=["properties"])


@router.get("", response_model=PropertyListResponse)
async def list_properties(
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """List all properties the current user has access to."""
    rows = await get_properties_by_user(client, current_user["id"])
    return PropertyListResponse(items=rows)


@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_new_property(
    payload: PropertyCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Create a new property (account + property record)."""
    data = payload.model_dump()
    prop = await create_property(client, current_user["id"], data)
    return prop


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get a single property by ID."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    prop = await get_property_by_id(client, property_id)
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return prop


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_existing_property(
    property_id: str,
    payload: PropertyUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Update a property."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    data = payload.model_dump(exclude_unset=True)
    if "address" in data and data["address"]:
        data["address"] = {k: v for k, v in data["address"].items() if v is not None}
    prop = await update_property(client, property_id, data)
    if not prop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return prop


@router.delete("/{property_id}", status_code=status.HTTP_200_OK)
async def delete_existing_property(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Delete a property and its associated account."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    deleted = await delete_property(client, property_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return {"message": "Property deleted", "id": property_id}
