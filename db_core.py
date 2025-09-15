from sqlmodel import SQLModel, Session, create_engine

# Single engine for the whole app
engine = create_engine("sqlite:///./app.db", connect_args={"check_same_thread": False})

def get_session():
    with Session(engine) as session:
        yield session