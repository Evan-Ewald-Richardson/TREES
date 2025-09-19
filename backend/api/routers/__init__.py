"""Aggregate API routers."""

from fastapi import APIRouter

from .auth import router as auth_router
from .courses import router as courses_router
from .gpx import router as gpx_router
from .leaderboard import router as leaderboard_router
from .strava import router as strava_router
from .system import router as system_router
from .users import router as users_router

ALL_ROUTERS: tuple[APIRouter, ...] = (
    system_router,
    gpx_router,
    courses_router,
    leaderboard_router,
    users_router,
    auth_router,
    strava_router,
)

__all__ = ["ALL_ROUTERS"]
