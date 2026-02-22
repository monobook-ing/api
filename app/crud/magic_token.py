from datetime import datetime

from supabase import Client
from postgrest.exceptions import APIError


async def create_magic_token(
    client: Client,
    *,
    email: str,
    token: str,
    expires_at: datetime,
    user_id: str | None = None,
) -> dict:
    """Create a magic token in Supabase. Deletes any existing tokens for the email first."""
    # Delete any existing tokens for this email to avoid unique constraint violation
    await delete_magic_tokens_by_email(client, email)
    
    token_data = {
        "email": email,
        "token": token,
        "expires_at": expires_at.isoformat(),
    }

    if user_id:
        token_data["user_id"] = user_id
    
    try:
        response = client.table("magic_tokens").insert(token_data).execute()
    except APIError as exc:
        # If the user_id violates a foreign key constraint (e.g., legacy data mismatch),
        # retry without the reference so sign-in isn't blocked for existing users.
        if "magic_tokens_user_id_fkey" in getattr(exc, "message", ""):
            token_data.pop("user_id", None)
            response = client.table("magic_tokens").insert(token_data).execute()
        else:
            raise
    
    if not response.data or len(response.data) == 0:
        raise ValueError("Failed to create magic token")
    
    return response.data[0]


async def get_magic_token_by_token(client: Client, token: str) -> dict | None:
    """Get magic token by token value from Supabase."""
    response = client.table("magic_tokens").select("*").eq("token", token).execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def get_magic_tokens_by_email(
    client: Client, email: str, *, active_only: bool = False
) -> list[dict]:
    """Get all magic tokens for an email from Supabase."""
    query = client.table("magic_tokens").select("*").eq("email", email)
    
    if active_only:
        now = datetime.utcnow().isoformat()
        query = query.is_("used_at", "null").gt("expires_at", now)
    
    response = query.order("expires_at", desc=True).execute()
    
    return response.data if response.data else []


async def mark_magic_token_used(client: Client, token: str) -> dict | None:
    """Mark a magic token as used in Supabase."""
    update_data = {
        "used_at": datetime.utcnow().isoformat(),
    }
    
    response = client.table("magic_tokens").update(update_data).eq("token", token).execute()
    
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


async def delete_magic_token(client: Client, token: str) -> bool:
    """Delete a specific magic token from Supabase."""
    response = client.table("magic_tokens").delete().eq("token", token).execute()
    return response.data is not None and len(response.data) > 0


async def delete_magic_tokens_by_email(client: Client, email: str) -> int:
    """Delete all magic tokens for an email from Supabase."""
    response = client.table("magic_tokens").delete().eq("email", email).execute()
    return len(response.data) if response.data else 0


async def delete_expired_tokens(client: Client) -> int:
    """Delete expired magic tokens from Supabase."""
    now = datetime.utcnow().isoformat()
    
    response = client.table("magic_tokens").delete().lt("expires_at", now).execute()
    
    return len(response.data) if response.data else 0
