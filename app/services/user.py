from supabase import Client

from app.crud.user import get_user_with_default_account, update_user
from app.schemas.user import UserMeResponse, UserUpdate


async def update_user_profile(
    client: Client, user_id: str, update_payload: UserUpdate
) -> UserMeResponse | None:
    """Update the current user's profile and return the latest details."""
    update_data = {
        key: value
        for key, value in update_payload.model_dump().items()
        if value is not None
    }

    if update_data:
        updated = await update_user(client, user_id=user_id, update_data=update_data)
        if not updated:
            return None

    # Always return the latest user details with default account info
    user_with_account = await get_user_with_default_account(client, user_id)
    if not user_with_account:
        return None

    return UserMeResponse(**user_with_account)
