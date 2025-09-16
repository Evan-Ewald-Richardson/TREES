"""
Database Core
SQLite database configuration and session management.
"""

import os
from sqlmodel import SQLModel, Session, create_engine

# Ensure data directory exists (relative to project root)
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(data_dir, exist_ok=True)

# Create SQLite engine (relative to project root)
db_path = os.path.join(data_dir, "app.db")
engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def get_session():
	"""Get database session dependency."""
	with Session(engine) as session:
		yield session