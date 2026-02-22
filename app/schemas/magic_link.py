from datetime import datetime

from pydantic import BaseModel, EmailStr


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    token: str
    expires_at: datetime


class MagicLinkConfirm(BaseModel):
    email: EmailStr
    token: str
