from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from supabase import Client

from app.core.security import decode_access_token
from app.crud.user import get_user_by_email
from app.db.base import get_supabase

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme), 
    client: Client = Depends(get_supabase)
) -> dict:
    """Get current user from JWT token using Supabase."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except (JWTError, ValueError):
        raise credentials_exception

    user = await get_user_by_email(client, email=email)
    if user is None:
        raise credentials_exception
    
    return user