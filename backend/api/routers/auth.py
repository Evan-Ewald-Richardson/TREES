"""OAuth authentication routes."""

from __future__ import annotations

import os
import uuid
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, func, select

from ...core import FRONTEND_ORIGIN, SUPER_USER_EMAILS, get_session
from ...models import OAuthUser

router = APIRouter(tags=["auth"])

_ADMIN_EMAILS = {email.strip().lower() for email in SUPER_USER_EMAILS if email}

oauth = OAuth()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OAUTH_REDIRECT_URL = os.getenv(
    "OAUTH_REDIRECT_URL", "http://127.0.0.1:3000/auth/google/callback"
)

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
else:  # pragma: no cover - allows app to boot without credentials
    oauth.register(
        name="google",
        client_id="dummy",
        client_secret="dummy",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _upsert_google_user(
    session: Session,
    *,
    email: str,
    sub: str,
    name: Optional[str],
    picture: Optional[str],
) -> OAuthUser:
    normalized_email = (email or "").strip().lower()
    email = normalized_email
    target_role = "admin" if normalized_email in _ADMIN_EMAILS else "user"

    user = session.exec(
        select(OAuthUser).where(func.lower(OAuthUser.email) == normalized_email)
    ).first()
    if user:
        changed = False
        if user.email != email:
            user.email = email
            changed = True
        if not user.provider_sub:
            user.provider_sub = sub
            changed = True
        if name and user.name != name:
            user.name = name
            changed = True
        if picture and user.avatar_url != picture:
            user.avatar_url = picture
            changed = True
        if user.role != target_role:
            user.role = target_role
            changed = True
        if changed:
            session.add(user)
            session.commit()
            session.refresh(user)
        return user

    user = OAuthUser(
        email=email,
        name=name,
        avatar_url=picture,
        provider="google",
        provider_sub=sub,
        role=target_role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user



@router.get("/auth/google/start")
async def auth_google_start(request: Request, next: str | None = None):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    if next:
        request.session["next"] = next
    try:
        return await oauth.google.authorize_redirect(request, OAUTH_REDIRECT_URL)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"OAuth error: {exc}") from exc


@router.get("/auth/google/callback")
async def auth_google_callback(
    request: Request, session: Session = Depends(get_session)
):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or await oauth.google.parse_id_token(request, token)
    email = userinfo.get("email")
    sub = userinfo.get("sub")
    name = userinfo.get("name") or (email.split("@")[0] if email else None)
    picture = userinfo.get("picture")
    if not email or not sub:
        raise HTTPException(status_code=400, detail="Unable to read Google profile.")

    user = _upsert_google_user(
        session, email=email, sub=sub, name=name, picture=picture
    )
    request.session["uid"] = str(user.id)
    request.session["name"] = user.name or user.email
    request.session["email"] = user.email
    request.session["role"] = user.role

    next_url = request.session.pop("next", None) or FRONTEND_ORIGIN
    if not str(next_url).startswith(FRONTEND_ORIGIN):
        next_url = FRONTEND_ORIGIN
    return RedirectResponse(next_url, status_code=302)


@router.post("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})


@router.get("/me")
def me(request: Request, session: Session = Depends(get_session)):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"user": None})
    try:
        user = session.get(OAuthUser, uuid.UUID(uid))
    except Exception:  # pragma: no cover - defensive
        request.session.clear()
        return JSONResponse({"user": None})
    if not user:
        request.session.clear()
        return JSONResponse({"user": None})
    return JSONResponse(
        {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name or user.email.split("@")[0],
                "avatar_url": user.avatar_url,
                "role": user.role,
            }
        }
    )


@router.get("/me/profile")
def me_profile(request: Request, session: Session = Depends(get_session)):
    """Get current OAuth user's profile with created courses and leaderboard entries."""

    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        oauth_user = session.get(OAuthUser, uuid.UUID(uid))
    except Exception:  # pragma: no cover - defensive
        request.session.clear()
        raise HTTPException(status_code=401, detail="Invalid session")

    if not oauth_user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="User not found")

    email_lower = (oauth_user.email or "").strip().lower()
    is_admin = oauth_user.role == "admin" or email_lower in _ADMIN_EMAILS

    user_name = oauth_user.name
    if user_name and " " in user_name:
        user_name = user_name.split(" ")[0]
    elif not user_name:
        user_name = (oauth_user.email or "").split("@")[0]
    user_name = (user_name or "").strip()

    from sqlalchemy import text

    if is_admin or not user_name:
        courses_sql = """
            SELECT id, name, buffer_m, gates_json, created_by, description, image_url, created_at
            FROM course
            ORDER BY id DESC
        """
        courses_params: dict[str, str] = {}
    else:
        courses_sql = """
            SELECT id, name, buffer_m, gates_json, created_by, description, image_url, created_at
            FROM course
            WHERE created_by = :user_name
            ORDER BY id DESC
        """
        courses_params = {"user_name": user_name}

    courses_result = session.execute(text(courses_sql), courses_params)

    import json as json_lib

    created_courses = []
    for row in courses_result:
        created_at = row.created_at
        if hasattr(created_at, "isoformat"):
            created_at_out = created_at.isoformat()
            if hasattr(created_at, "tzinfo") and not created_at.tzinfo:
                created_at_out += "Z"
        else:
            created_at_out = created_at
        created_courses.append(
            {
                "id": row.id,
                "name": row.name,
                "buffer_m": row.buffer_m,
                "gates": json_lib.loads(row.gates_json or "[]"),
                "created_by": row.created_by,
                "description": row.description,
                "image_url": row.image_url,
                "created_at": created_at_out,
            }
        )

    leaderboard_result = session.execute(
        text(
            """
            SELECT le.id, le.course_id, le.total_time_sec, le.created_at,
                   c.name AS course_name,
                   (SELECT COUNT(*) FROM leaderboardentry le2
                    WHERE le2.course_id = le.course_id
                      AND le2.total_time_sec < le.total_time_sec) + 1 AS rank
            FROM leaderboardentry le
            JOIN course c ON c.id = le.course_id
            WHERE le.username = :user_name
            ORDER BY le.total_time_sec
            """
        ),
        {"user_name": user_name},
    )

    leaderboard_positions = []
    for row in leaderboard_result:
        created_at = row.created_at
        if hasattr(created_at, "isoformat"):
            created_at_out = created_at.isoformat()
            if hasattr(created_at, "tzinfo") and not created_at.tzinfo:
                created_at_out += "Z"
        else:
            created_at_out = created_at
        leaderboard_positions.append(
            {
                "id": row.id,
                "courseId": row.course_id,
                "courseName": row.course_name,
                "rank": row.rank,
                "time": row.total_time_sec,
                "created_at": created_at_out,
            }
        )

    return JSONResponse(
        {
            "createdCourses": created_courses,
            "leaderboardPositions": leaderboard_positions,
            "isAdmin": is_admin,
        }
    )





__all__ = ["router"]
