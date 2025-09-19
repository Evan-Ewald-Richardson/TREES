"""Application settings and environment helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv

load_dotenv(override=False)


def _require_env(name: str) -> str:
    """Return a required environment variable or raise an error."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


# Strava OAuth configuration -------------------------------------------------
_STRAVA_CLIENT_ID_RAW = _require_env("STRAVA_CLIENT_ID")
try:
    STRAVA_CLIENT_ID = int(_STRAVA_CLIENT_ID_RAW)
except ValueError as exc:  # pragma: no cover - defensive guard
    raise RuntimeError("STRAVA_CLIENT_ID must be an integer") from exc

STRAVA_CLIENT_SECRET = _require_env("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = _require_env("STRAVA_REDIRECT_URI")


# Application security -------------------------------------------------------
SECRET_KEY = _require_env("SECRET_KEY")

# FRONTEND_ORIGIN can contain a comma-separated list for multi-domain deploys.
_frontend_origins = _split_csv(_require_env("FRONTEND_ORIGIN"))
_additional_origins = _split_csv(os.getenv("ADDITIONAL_ALLOWED_ORIGINS"))

_local_dev_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

ALLOWED_CORS_ORIGINS = _unique(
    [
        *_frontend_origins,
        *_additional_origins,
        *_local_dev_origins,
    ]
)

FRONTEND_ORIGINS = _frontend_origins
FRONTEND_ORIGIN = FRONTEND_ORIGINS[0] if FRONTEND_ORIGINS else ""


# Runtime behaviour ----------------------------------------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "")
SUPER_USER_NAME = os.getenv("SUPER_USER_NAME", "EVERGREEN")

_super_user_emails_env = _split_csv(os.getenv("SUPER_USER_EMAILS"))
SUPER_USER_EMAILS = _unique(
    [email for email in ["evrichard.02@gmail.com", *_super_user_emails_env] if email]
)

COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
COOKIE_SECURE = _env_bool("COOKIE_SECURE", False)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
DB_RESET = _env_bool("DB_RESET", False)


__all__ = [
    "ALLOWED_CORS_ORIGINS",
    "BACKEND_URL",
    "COOKIE_DOMAIN",
    "COOKIE_SAMESITE",
    "COOKIE_SECURE",
    "DB_RESET",
    "FRONTEND_ORIGIN",
    "FRONTEND_ORIGINS",
    "SECRET_KEY",
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_REDIRECT_URI",
    "SUPER_USER_EMAILS",
    "SUPER_USER_NAME",
    "UPLOAD_DIR",
]
