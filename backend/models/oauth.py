"""Database model for OAuth-backed accounts."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlmodel import Field, SQLModel


class OAuthUser(SQLModel, table=True):
    """User authenticated via OAuth provider."""

    __tablename__ = "oauth_user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, nullable=False)
    email: str = Field(index=True, unique=True)
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str = Field(default="google")
    provider_sub: Optional[str] = Field(default=None, index=True)
    role: str = Field(default="user")


__all__ = ["OAuthUser"]
