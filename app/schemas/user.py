from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True


class UserMeResponse(BaseModel):
    """Response schema for /users/me endpoint"""
    email: str
    first_name: str | None = None
    last_name: str | None = None
    default_account_id: str | None = None


class UserUpdate(BaseModel):
    """Schema for updating user profile details."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_and_validate(cls, value: str | None) -> str | None:
        if value is None:
            return value

        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")

        return stripped
