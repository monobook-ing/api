from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.db.base import Base


class MagicToken(Base):
    __tablename__ = "magic_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
