# strava_client.py
from __future__ import annotations
import os
import time
from typing import Any, Dict, Optional, Tuple
import httpx

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:3000/api/strava/callback")

AUTH_BASE = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE = "https://www.strava.com/api/v3"

SCOPES = "read,activity:read"  # add activity:read_all if you need private activities

def auth_url(state: str = "state1") -> str:
    return (
        f"{AUTH_BASE}?client_id={STRAVA_CLIENT_ID}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code&approval_prompt=auto"
        f"&scope={SCOPES}&state={state}"
    )

async def exchange_code_for_token(code: str) -> Dict[str, Any]:
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
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {access_token}"}, params=params or {})
        return r