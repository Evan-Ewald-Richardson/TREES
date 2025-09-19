"""Database models for course entities."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field as ORMField, SQLModel

from ..core.time import utcnow


class Course(SQLModel, table=True):
    """Race course definition with gate metadata."""

    id: Optional[int] = ORMField(default=None, primary_key=True)
    name: str
    buffer_m: int = 10
    gates_json: str
    created_by: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime = ORMField(default_factory=utcnow)


__all__ = ["Course"]
