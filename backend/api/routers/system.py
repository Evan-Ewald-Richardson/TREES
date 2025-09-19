"""System-level API endpoints."""

from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...core import BACKEND_URL, SUPER_USER_NAME

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> Dict[str, bool]:
    """Simple readiness probe."""

    return {"ok": True}


@router.get("/healthz")
def healthz() -> JSONResponse:
    """Kubernetes-style readiness endpoint."""

    return JSONResponse({"ok": True})


@router.get("/config")
def get_config() -> Dict[str, str]:
    """Expose frontend configuration values."""

    return {
        "backend_url": BACKEND_URL,
        "super_user_name": SUPER_USER_NAME,
    }


@router.get("/_debug/cors")
def debug_cors(request: Request) -> Dict[str, Optional[str]]:
    """Report headers relevant to CORS troubleshooting."""

    return {
        "seen_origin": request.headers.get("origin"),
        "acr_method": request.headers.get("access-control-request-method"),
        "acr_headers": request.headers.get("access-control-request-headers"),
    }


__all__ = ["router"]
