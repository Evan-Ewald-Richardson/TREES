from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field as ORMField

class StravaToken(SQLModel, table=True):
    id: Optional[int] = ORMField(default=None, primary_key=True)
    athlete_id: int
    athlete_username: Optional[str] = None
    access_token: str
    refresh_token: str
    expires_at: int  # unix seconds
    scope: Optional[str] = None
    created_at: datetime = ORMField(default_factory=datetime.utcnow)