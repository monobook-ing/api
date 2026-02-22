from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.crud.host_profile import get_host_profile, upsert_host_profile
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.host_profile import HostProfileResponse, HostProfileUpdate

router = APIRouter(prefix="/v1.0/properties/{property_id}/host-profile", tags=["host-profile"])


@router.get("", response_model=HostProfileResponse)
async def get_profile(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Get host profile for a property."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    profile = await get_host_profile(client, property_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host profile not found")
    return profile


@router.put("", response_model=HostProfileResponse)
async def update_profile(
    property_id: str,
    payload: HostProfileUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Create or update host profile for a property."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    data = payload.model_dump(exclude_unset=True)
    profile = await upsert_host_profile(client, property_id, data)
    return profile
