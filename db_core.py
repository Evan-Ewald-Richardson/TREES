from sqlmodel import SQLModel, Session, create_engine
import os

os.makedirs("data", exist_ok=True)  # ensure a writeable folder exists

engine = create_engine("sqlite:///./data/app.db", connect_args={"check_same_thread": False})


def get_session():
    with Session(engine) as session:
        yield session