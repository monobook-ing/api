from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator


class TeamMemberInvite(BaseModel):
    """Request schema for inviting a team member"""
    email: EmailStr
    role: str

    @field_validator("role")
    @classmethod
    def validate_invited_role(cls, value: str) -> str:
        """Validate and normalize invited team member role."""
        normalized = value.lower()
        allowed_roles = {"admin", "guest"}

        if normalized == "owner":
            raise ValueError("Inviting a team member with the owner role is not allowed")
        if normalized not in allowed_roles:
            raise ValueError("Invalid role value. Allowed roles: admin, guest")

        return normalized


class TeamMemberResponse(BaseModel):
    """Response schema for team member details"""
    id: str
    role: str
    user_id: str
    status: str
    name: str | None
    first_name: str | None = None
    last_name: str | None = None
    joined_at: datetime


class TeamMemberUpdate(BaseModel):
    """Request schema for updating a team member"""
    role: str | None = None
    status: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        """Validate and normalize role updates."""
        if value is None:
            return value

        normalized = value.lower()
        allowed_roles = {"admin", "guest"}

        if normalized not in allowed_roles:
            raise ValueError("Invalid role value. Allowed roles: admin, guest")

        return normalized


class TeamMemberListResponse(BaseModel):
    """Response schema for paginated team member results."""

    items: list[TeamMemberResponse]
    next_cursor: str | None
