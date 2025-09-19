"""Database model for leaderboard results."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field as ORMField, SQLModel

from ..core.time import utcnow


class LeaderboardEntry(SQLModel, table=True):
    """Leaderboard entry model for storing race results."""

    id: Optional[int] = ORMField(default=None, primary_key=True)
    course_id: int = ORMField(index=True)
    username: str
    total_time_sec: int
    segment_times_json: str
    created_at: datetime = ORMField(default_factory=utcnow)


__all__ = ["LeaderboardEntry"]
