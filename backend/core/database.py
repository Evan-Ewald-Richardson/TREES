"""Database configuration and session helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, create_engine

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _PROJECT_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_DB_PATH = _DATA_DIR / "app.db"
engine = create_engine(
    f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False}
)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""

    with Session(engine) as session:
        yield session


__all__ = ["engine", "get_session"]
