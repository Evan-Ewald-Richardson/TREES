"""
Strava Routes
OAuth authentication and activity data endpoints for Strava integration.
"""

from __future__ import annotations
import time
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.responses import RedirectResponse, JSONResponse
from sqlmodel import Session, select

from .settings import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI
from .models_strava import StravaToken
from .strava_client import auth_url, exchange_code_for_token, refresh_access_token, api_get
from .db_core import get_session

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

router = APIRouter(prefix="/api/strava", tags=["strava"])

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
# OAuth Flow
# =============================================================================


@router.get("/connect")
def strava_connect():
	"""Initiate Strava OAuth connection."""
	# Validate configuration
	if not isinstance(STRAVA_CLIENT_ID, int) or STRAVA_CLIENT_ID <= 0:
		raise HTTPException(status_code=500, detail="STRAVA_CLIENT_ID misconfigured")

	# OAuth parameters
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
	# Extract athlete data
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

	# Store token ID in session
	request.session["strava_token_id"] = token.id
	# Redirect back to frontend
	return RedirectResponse(url=f"{FRONTEND_ORIGIN}/?strava=ok", status_code=307)


@router.post("/logout")
async def strava_logout(request: Request):
	"""Logout and clear session."""
	request.session.pop("strava_token_id", None)
	return {"ok": True}

# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/me")
async def me(request: Request, session: Session = Depends(get_session)):
	"""Get current athlete information."""
	token = await _get_token_from_session(request, session)
	if not token:
		raise HTTPException(401, "Not connected")
	token = await _ensure_valid_token(token, session)
	r = await api_get(token.access_token, "/athlete")
	if r.status_code == 401:
		# Stale credentials
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
	# Extract essential data for listing
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

	# Fetch streams (time, latlng, altitude)
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
		# Only keep points we can timestamp
		if tsec is None:
			continue
		t_iso = datetime.utcfromtimestamp((start_ms/1000.0) + tsec).isoformat() + "Z"
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
		"redirect_uri": STRAVA_REDIRECT_URI
	})