"""FastAPI application factory and configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from starlette.middleware.sessions import SessionMiddleware

from . import models  # noqa: F401 - ensure models are registered with SQLModel
from .api import register_routes
from .core import (
    ALLOWED_CORS_ORIGINS,
    COOKIE_DOMAIN,
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    DB_RESET,
    SECRET_KEY,
    UPLOAD_DIR,
    engine,
)


UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DB_RESET:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="GPX Leaderboard API", version="0.2.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        session_cookie="sid",
        https_only=COOKIE_SECURE,
        same_site=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
    )

    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=3000, reload=True)
