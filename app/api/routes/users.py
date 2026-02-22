from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
from app.crud.user import get_user_with_default_account
from app.db.base import get_supabase
from app.schemas.user import UserMeResponse, UserUpdate
from app.services.user import update_user_profile

router = APIRouter(prefix="/v1.0/users", tags=["users"])


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_details(
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase)
) -> UserMeResponse:
    """Get current user details with default account."""
    user_data = await get_user_with_default_account(client, current_user["id"])
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserMeResponse(**user_data)


@router.patch("/me", response_model=UserMeResponse)
async def update_current_user_details(
    payload: UserUpdate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase)
) -> UserMeResponse:
    """Update current user's profile information."""
    updated_user = await update_user_profile(client, current_user["id"], payload)

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return updated_user
