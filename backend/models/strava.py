"""Database model for Strava OAuth tokens."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field as ORMField, SQLModel

from ..core.time import utcnow


class StravaToken(SQLModel, table=True):
    """Persists Strava OAuth credentials."""

    id: Optional[int] = ORMField(default=None, primary_key=True)
    athlete_id: int
    athlete_username: Optional[str] = None
    access_token: str
    refresh_token: str
    expires_at: int
    scope: Optional[str] = None
    created_at: datetime = ORMField(default_factory=utcnow)


__all__ = ["StravaToken"]
