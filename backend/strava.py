"""
Strava Integration
Complete Strava OAuth authentication and API integration in one place.
"""

from __future__ import annotations
import time
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import SQLModel, Field as ORMField, Session, select

from .db_core import get_session
from .settings import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI

# =============================================================================
# Configuration
# =============================================================================

from .settings import FRONTEND_ORIGIN

# Strava API endpoints
AUTH_BASE = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"
SCOPES = "read,activity:read"

# =============================================================================
# Database Model
# =============================================================================

class StravaToken(SQLModel, table=True):
	"""Strava OAuth token storage model."""
	id: Optional[int] = ORMField(default=None, primary_key=True)
	athlete_id: int
	athlete_username: Optional[str] = None
	access_token: str
	refresh_token: str
	expires_at: int  # Unix timestamp
	scope: Optional[str] = None
	created_at: datetime = ORMField(default_factory=datetime.now(timezone.utc))

# =============================================================================
# API Client Functions
# =============================================================================

def auth_url(state: str = "state1") -> str:
	"""Generate Strava OAuth authorization URL."""
	return (
		f"{AUTH_BASE}?client_id={STRAVA_CLIENT_ID}"
		f"&redirect_uri={STRAVA_REDIRECT_URI}"
		f"&response_type=code&approval_prompt=auto"
		f"&scope={SCOPES}&state={state}"
	)

async def exchange_code_for_token(code: str) -> Dict[str, Any]:
	"""Exchange authorization code for access token."""
	async with httpx.AsyncClient(timeout=20) as client:
		r = await client.post(TOKEN_URL, data={
			"client_id": STRAVA_CLIENT_ID,
			"client_secret": STRAVA_CLIENT_SECRET,
			"code": code,
			"grant_type": "authorization_code",
		})
		r.raise_for_status()
		return r.json()

async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
	"""Refresh expired access token."""
	async with httpx.AsyncClient(timeout=20) as client:
		r = await client.post(TOKEN_URL, data={
			"client_id": STRAVA_CLIENT_ID,
			"client_secret": STRAVA_CLIENT_SECRET,
			"grant_type": "refresh_token",
			"refresh_token": refresh_token,
		})
		r.raise_for_status()
		return r.json()

async def api_get(access_token: str, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
	"""Make authenticated GET request to Strava API."""
	url = f"{API_BASE}{path}"
	async with httpx.AsyncClient(timeout=30) as client:
		r = await client.get(url, headers={"Authorization": f"Bearer {access_token}"}, params=params or {})
		return r

# =============================================================================
# Helper Functions
# =============================================================================

async def _get_token_from_session(request: Request, session: Session) -> Optional[StravaToken]:
	"""Get Strava token from session."""
	token_id = request.session.get("strava_token_id")
	if not token_id:
		return None
	token = session.get(StravaToken, int(token_id))
	return token

async def _ensure_valid_token(token: StravaToken, session: Session) -> StravaToken:
	"""Ensure token is valid, refresh if needed."""
	now = int(time.time())
	if token.expires_at - 60 > now:
		return token
	# Refresh token
	data = await refresh_access_token(token.refresh_token)
	token.access_token = data["access_token"]
	token.refresh_token = data.get("refresh_token", token.refresh_token)
	token.expires_at = int(data["expires_at"])
	session.add(token)
	session.commit()
	session.refresh(token)
	return token

# =============================================================================
# FastAPI Router
# =============================================================================

router = APIRouter(prefix="/api/strava", tags=["strava"])

# OAuth Flow
@router.get("/connect")
def strava_connect():
	"""Initiate Strava OAuth connection."""
	if not isinstance(STRAVA_CLIENT_ID, int) or STRAVA_CLIENT_ID <= 0:
		raise HTTPException(status_code=500, detail="STRAVA_CLIENT_ID misconfigured")
	
	params = {
		"client_id": STRAVA_CLIENT_ID,
		"response_type": "code",
		"redirect_uri": STRAVA_REDIRECT_URI,
		"approval_prompt": "auto",
		"scope": "read,activity:read",
	}
	url = "https://www.strava.com/oauth/authorize?" + urlencode(params)
	return RedirectResponse(url)

@router.get("/login")
async def strava_login():
	"""Alternative login endpoint using auth_url helper."""
	return RedirectResponse(auth_url(state="ok"))

@router.get("/callback")
async def strava_callback(code: Optional[str] = None, error: Optional[str] = None, request: Request = None, session: Session = Depends(get_session)):
	"""Handle OAuth callback from Strava."""
	if error:
		raise HTTPException(400, detail=f"Strava error: {error}")
	if not code:
		raise HTTPException(400, detail="Missing code")

	data = await exchange_code_for_token(code)
	athlete = data.get("athlete") or {}
	token = StravaToken(
		athlete_id=int(athlete.get("id")),
		athlete_username=athlete.get("username") or athlete.get("firstname") or "athlete",
		access_token=data["access_token"],
		refresh_token=data["refresh_token"],
		expires_at=int(data["expires_at"]),
		scope=",".join(data.get("scope", [])) if isinstance(data.get("scope"), list) else (data.get("scope") or ""),
	)
	session.add(token)
	session.commit()
	session.refresh(token)

	request.session["strava_token_id"] = token.id
	frontend_origin = FRONTEND_ORIGIN.rstrip('/')
	redirect_url = f"{frontend_origin}/?strava=ok"
	return RedirectResponse(url=redirect_url, status_code=307)

@router.post("/logout")
async def strava_logout(request: Request):
	"""Logout and clear session."""
	request.session.pop("strava_token_id", None)
	return {"ok": True}

# API Endpoints
@router.get("/me")
async def me(request: Request, session: Session = Depends(get_session)):
	"""Get current athlete information."""
	token = await _get_token_from_session(request, session)
	if not token:
		raise HTTPException(401, "Not connected")
	token = await _ensure_valid_token(token, session)
	r = await api_get(token.access_token, "/athlete")
	if r.status_code == 401:
		request.session.pop("strava_token_id", None)
		raise HTTPException(401, "Not connected")
	r.raise_for_status()
	return r.json()

@router.get("/activities")
async def activities(request: Request, session: Session = Depends(get_session), page: int = 1, per_page: int = 20):
	"""Get list of athlete activities."""
	token = await _get_token_from_session(request, session)
	if not token:
		raise HTTPException(401, "Not connected")
	token = await _ensure_valid_token(token, session)
	r = await api_get(token.access_token, "/athlete/activities", params={"page": page, "per_page": per_page})
	if r.status_code == 401:
		request.session.pop("strava_token_id", None)
		raise HTTPException(401, "Not connected")
	r.raise_for_status()
	
	items = []
	for a in r.json():
		items.append({
			"id": a["id"],
			"name": a.get("name") or f"Activity {a['id']}",
			"start_date": a.get("start_date"),
			"sport_type": a.get("sport_type"),
			"distance": a.get("distance"),
			"has_heartrate": a.get("has_heartrate", False),
		})
	return {"activities": items}

@router.get("/activities/{activity_id}/points")
async def activity_points(activity_id: int, request: Request, session: Session = Depends(get_session)):
	"""Get track points for a specific activity."""
	token = await _get_token_from_session(request, session)
	if not token:
		raise HTTPException(401, "Not connected")
	token = await _ensure_valid_token(token, session)

	# Load activity to get start date
	r_act = await api_get(token.access_token, f"/activities/{activity_id}")
	r_act.raise_for_status()
	act = r_act.json()
	start_ms = int(datetime.fromisoformat(act["start_date"].replace("Z", "+00:00")).timestamp() * 1000)

	# Fetch streams
	r = await api_get(token.access_token, f"/activities/{activity_id}/streams", params={
		"keys": "time,latlng,altitude",
		"key_by_type": "true",
	})
	r.raise_for_status()
	js = r.json()

	time_stream = (js.get("time") or {}).get("data") or []
	latlngs = (js.get("latlng") or {}).get("data") or []
	alts = (js.get("altitude") or {}).get("data") or []

	points = []
	for i, ll in enumerate(latlngs):
		tsec = time_stream[i] if i < len(time_stream) else None
		ele = alts[i] if i < len(alts) else None
		if tsec is None:
			continue
		t_iso = datetime.now(timezone.utc)fromtimestamp((start_ms/1000.0) + tsec).isoformat() + "Z"
		points.append({
			"lat": ll[0],
			"lon": ll[1],
			"ele": float(ele) if ele is not None else None,
			"time": t_iso
		})

	return {"points": points, "name": act.get("name") or f"Activity {activity_id}"}

@router.get("/debug-config")
def strava_debug_config():
	"""Debug configuration (no secrets)."""
	return JSONResponse({
		"client_id": STRAVA_CLIENT_ID,
		"redirect_uri": STRAVA_REDIRECT_URI,
		"frontend_origin": FRONTEND_ORIGIN,
		"auth_url": auth_url("test")
	})

