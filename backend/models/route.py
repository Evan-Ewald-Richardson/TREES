"""Database model for storing submitted route data tied to leaderboard entries."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field as ORMField, SQLModel

from ..core.time import utcnow


class LeaderboardRoute(SQLModel, table=True):
    """Serialized route geometry captured from a leaderboard submission."""

    id: Optional[int] = ORMField(default=None, primary_key=True)
    leaderboard_entry_id: int = ORMField(
        foreign_key="leaderboardentry.id",
        unique=True,
        index=True,
    )
    course_id: int = ORMField(index=True)
    username: str = ORMField(max_length=64)
    points_json: str = ORMField(sa_column=Column(Text, nullable=False))
    created_at: datetime = ORMField(default_factory=utcnow)
    updated_at: datetime = ORMField(default_factory=utcnow)

    def touch(self) -> None:
        """Update the timestamp to reflect a modification."""

        self.updated_at = utcnow()


__all__ = ["LeaderboardRoute"]
