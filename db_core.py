"""
Database Core
SQLite database configuration and session management.
"""

import os
from sqlmodel import SQLModel, Session, create_engine

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

# Create SQLite engine
engine = create_engine("sqlite:///./data/app.db", connect_args={"check_same_thread": False})


def get_session():
	"""Get database session dependency."""
	with Session(engine) as session:
		yield session