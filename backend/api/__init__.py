"""API assembly helpers."""

from __future__ import annotations

from fastapi import FastAPI

from .routers import ALL_ROUTERS


def register_routes(app: FastAPI) -> None:
    """Attach all application routers to the given app."""

    for router in ALL_ROUTERS:
        app.include_router(router)


__all__ = ["register_routes"]
