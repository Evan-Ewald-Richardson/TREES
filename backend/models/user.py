"""Database model for leaderboard users."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field as ORMField, SQLModel

from ..core.time import utcnow


class User(SQLModel, table=True):
    """Participant identified by display name."""

    id: Optional[int] = ORMField(default=None, primary_key=True)
    name: str = ORMField(index=True, unique=True)
    created_at: datetime = ORMField(default_factory=utcnow)


__all__ = ["User"]
