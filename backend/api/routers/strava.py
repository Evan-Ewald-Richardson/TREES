"""Strava integration routes."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select

from ...core import (
    FRONTEND_ORIGIN,
    STRAVA_CLIENT_ID,
    STRAVA_CLIENT_SECRET,
    STRAVA_REDIRECT_URI,
    get_session,
    utcnow,
)
from ...models import StravaToken

router = APIRouter(prefix="/api/strava", tags=["strava"])

AUTH_BASE = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"
SCOPES = "read,activity:read"


def auth_url(state: str = "state1") -> str:
    """Generate Strava OAuth authorization URL."""

    return (
        f"{AUTH_BASE}?client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code&approval_prompt=auto"
        f"&scope={SCOPES}&state={state}"
    )


async def exchange_code_for_token(code: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        return response.json()


async def api_get(
    access_token: str, path: str, params: Optional[Dict[str, Any]] = None
) -> httpx.Response:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params or {},
        )


async def _get_token_from_session(
    request: Request, session: Session
) -> Optional[StravaToken]:
    token_id = request.session.get("strava_token_id")
    if not token_id:
        return None
    return session.get(StravaToken, int(token_id))


async def _ensure_valid_token(token: StravaToken, session: Session) -> StravaToken:
    if token.expires_at > int(time.time()) + 60:
        return token

    refreshed = await refresh_access_token(token.refresh_token)
    token.access_token = refreshed["access_token"]
    token.refresh_token = refreshed["refresh_token"]
    token.expires_at = refreshed["expires_at"]
    token.scope = refreshed.get("scope")
    session.add(token)
    session.commit()
    session.refresh(token)
    return token


@router.get("/auth-url")
def strava_auth_url(state: str = "state1") -> Dict[str, str]:
    return {"auth_url": auth_url(state)}


@router.get("/callback")
async def strava_callback(
    code: str,
    scope: str,
    state: str,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    token_data = await exchange_code_for_token(code)

    athlete = token_data.get("athlete") or {}
    athlete_id = athlete.get("id")
    athlete_username = athlete.get("username") or athlete.get("firstname")

    existing = session.exec(
        select(StravaToken).where(StravaToken.athlete_id == athlete_id)
    ).first()

    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data["refresh_token"]
        existing.expires_at = token_data["expires_at"]
        existing.scope = scope
        existing.athlete_username = athlete_username
        session.add(existing)
        session.commit()
        session.refresh(existing)
        token = existing
    else:
        token = StravaToken(
            athlete_id=athlete_id,
            athlete_username=athlete_username,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
            scope=scope,
        )
        session.add(token)
        session.commit()
        session.refresh(token)

    request.session["strava_token_id"] = token.id

    next_url = request.session.pop("next", None) or f"{FRONTEND_ORIGIN}/strava"
    if not str(next_url).startswith(FRONTEND_ORIGIN):
        next_url = f"{FRONTEND_ORIGIN}/strava"
    return RedirectResponse(next_url)


@router.get("/disconnect")
def strava_disconnect(request: Request, session: Session = Depends(get_session)):
    token_id = request.session.pop("strava_token_id", None)
    if token_id:
        token = session.get(StravaToken, int(token_id))
        if token:
            session.delete(token)
            session.commit()
    return {"ok": True}


@router.get("/me")
async def me(request: Request, session: Session = Depends(get_session)):
    token = await _get_token_from_session(request, session)
    if not token:
        raise HTTPException(401, "Not connected")
    token = await _ensure_valid_token(token, session)
    response = await api_get(token.access_token, "/athlete")
    if response.status_code == 401:
        request.session.pop("strava_token_id", None)
        raise HTTPException(401, "Not connected")
    response.raise_for_status()
    return response.json()


@router.get("/activities")
async def activities(
    request: Request,
    session: Session = Depends(get_session),
    page: int = 1,
    per_page: int = 20,
):
    token = await _get_token_from_session(request, session)
    if not token:
        raise HTTPException(401, "Not connected")
    token = await _ensure_valid_token(token, session)
    response = await api_get(
        token.access_token,
        "/athlete/activities",
        params={"page": page, "per_page": per_page},
    )
    if response.status_code == 401:
        request.session.pop("strava_token_id", None)
        raise HTTPException(401, "Not connected")
    response.raise_for_status()

    items: List[Dict[str, Any]] = []
    for activity in response.json():
        items.append(
            {
                "id": activity["id"],
                "name": activity.get("name") or f"Activity {activity['id']}",
                "start_date": activity.get("start_date"),
                "sport_type": activity.get("sport_type"),
                "distance": activity.get("distance"),
                "has_heartrate": activity.get("has_heartrate", False),
            }
        )
    return {"activities": items}


@router.get("/activities/{activity_id}/points")
async def activity_points(
    activity_id: int, request: Request, session: Session = Depends(get_session)
):
    token = await _get_token_from_session(request, session)
    if not token:
        raise HTTPException(401, "Not connected")
    token = await _ensure_valid_token(token, session)

    activity_response = await api_get(token.access_token, f"/activities/{activity_id}")
    activity_response.raise_for_status()
    activity = activity_response.json()
    start_ms = int(
        datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00")).timestamp()
        * 1000
    )

    streams_response = await api_get(
        token.access_token,
        f"/activities/{activity_id}/streams",
        params={"keys": "time,latlng,altitude", "key_by_type": "true"},
    )
    streams_response.raise_for_status()
    streams = streams_response.json()

    time_stream = (streams.get("time") or {}).get("data") or []
    latlngs = (streams.get("latlng") or {}).get("data") or []
    alts = (streams.get("altitude") or {}).get("data") or []

    points: List[Dict[str, Any]] = []
    for idx, latlng in enumerate(latlngs):
        elapsed = time_stream[idx] if idx < len(time_stream) else None
        elevation = alts[idx] if idx < len(alts) else None
        if elapsed is None:
            continue
        timestamp = (start_ms / 1000.0) + elapsed
        iso_time = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        points.append(
            {
                "lat": latlng[0],
                "lon": latlng[1],
                "ele": float(elevation) if elevation is not None else None,
                "time": iso_time,
            }
        )

    return {"points": points, "name": activity.get("name") or f"Activity {activity_id}"}


@router.get("/debug-config")
def strava_debug_config():
    return JSONResponse(
        {
            "client_id": STRAVA_CLIENT_ID,
            "redirect_uri": STRAVA_REDIRECT_URI,
            "frontend_origin": FRONTEND_ORIGIN,
            "auth_url": auth_url("test"),
        }
    )


__all__ = ["router"]
