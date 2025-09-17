# backend/routers/auth.py
import os, uuid
from fastapi import APIRouter, Request, Depends, HTTPException
from starlette.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth

from sqlmodel import SQLModel, Field, Session, create_engine, select

# Import existing database setup
from ..db_core import engine, get_session

class OAuthUser(SQLModel, table=True):
    __tablename__ = "oauth_user"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, nullable=False)
    email: str = Field(index=True, unique=True)
    name: str | None = None
    avatar_url: str | None = None
    provider: str = Field(default="google")
    provider_sub: str | None = Field(default=None, index=True)
    role: str = Field(default="user")  # 'user'|'group_admin'|'admin'|'super'

SQLModel.metadata.create_all(engine)

oauth = OAuth()

# Check for required environment variables
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print(f"Warning: Google OAuth not configured. GOOGLE_CLIENT_ID: {'✓' if GOOGLE_CLIENT_ID else '✗'}, GOOGLE_CLIENT_SECRET: {'✓' if GOOGLE_CLIENT_SECRET else '✗'}")
    # Create a dummy OAuth registration to prevent errors
    oauth.register(
        name="google",
        client_id="dummy",
        client_secret="dummy",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
else:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

from backend.settings import FRONTEND_ORIGIN
OAUTH_REDIRECT_URL = os.getenv("OAUTH_REDIRECT_URL", "http://127.0.0.1:3000/auth/google/callback")

router = APIRouter(tags=["auth"])

def upsert_google_user(session: Session, email: str, sub: str, name: str | None, picture: str | None) -> OAuthUser:
    user = session.exec(select(OAuthUser).where(OAuthUser.email == email)).first()
    if user:
        changed = False
        if not user.provider_sub:
            user.provider_sub = sub; changed = True
        if name and user.name != name:
            user.name = name; changed = True
        if picture and user.avatar_url != picture:
            user.avatar_url = picture; changed = True
        if changed:
            session.add(user); session.commit(); session.refresh(user)
        return user
    user = OAuthUser(email=email, name=name, avatar_url=picture, provider="google", provider_sub=sub)
    session.add(user); session.commit(); session.refresh(user)
    return user

@router.get("/auth/google/start")
async def auth_google_start(request: Request, next: str | None = None):
    try:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Google OAuth not configured. Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")
        
        if next:
            request.session["next"] = next
        return await oauth.google.authorize_redirect(request, OAUTH_REDIRECT_URL)
    except Exception as e:
        print(f"OAuth start error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth error: {str(e)}")

@router.get("/auth/google/callback")
async def auth_google_callback(request: Request, session: Session = Depends(get_session)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or await oauth.google.parse_id_token(request, token)
    email = userinfo.get("email"); sub = userinfo.get("sub")
    name = userinfo.get("name") or (email.split("@")[0] if email else None)
    picture = userinfo.get("picture")
    if not email or not sub:
        raise HTTPException(status_code=400, detail="Unable to read Google profile.")
    user = upsert_google_user(session, email=email, sub=sub, name=name, picture=picture)
    request.session["uid"] = str(user.id)
    request.session["name"] = user.name or user.email
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
    except Exception:
        request.session.clear()
        return JSONResponse({"user": None})
    if not user:
        request.session.clear()
        return JSONResponse({"user": None})
    return JSONResponse({"user": {
        "id": str(user.id),
        "email": user.email,
        "name": user.name or user.email.split("@")[0],
        "avatar_url": user.avatar_url,
        "role": user.role,
    }})

@router.get("/me/profile")
def me_profile(request: Request, session: Session = Depends(get_session)):
    """Get current OAuth user's profile with courses and leaderboard entries."""
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        oauth_user = session.get(OAuthUser, uuid.UUID(uid))
    except Exception:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Invalid session")
    
    if not oauth_user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="User not found")
    
    # Get the consistent username for backend operations
    user_name = oauth_user.name
    if user_name and ' ' in user_name:
        user_name = user_name.split(' ')[0]  # "Evan Richardson" -> "Evan"
    elif not user_name:
        user_name = oauth_user.email.split('@')[0]
    
    # Use raw SQL to avoid circular imports - query the tables directly
    from sqlalchemy import text

    # Get user's created courses with full fields
    courses_result = session.execute(
        text("""
        SELECT id, name, buffer_m, gates_json, created_by, description, image_url, created_at
        FROM course
        WHERE created_by = :user_name
        ORDER BY id DESC
        """),
        {"user_name": user_name}
    )

    import json as _json
    created_courses = []
    for row in courses_result:
        _created_at = row.created_at
        if isinstance(_created_at, str):
            created_at_out = _created_at
        elif _created_at is not None:
            try:
                created_at_out = _created_at.isoformat() + ("" if _created_at.tzinfo else "Z")
            except Exception:
                created_at_out = str(_created_at)
        else:
            created_at_out = None

        created_courses.append({
            "id": row.id,
            "name": row.name,
            "buffer_m": row.buffer_m,
            "gates": _json.loads(row.gates_json or "[]"),
            "created_by": row.created_by,
            "description": row.description,
            "image_url": row.image_url,
            "created_at": created_at_out,
        })

    # Get user's leaderboard positions (table name is 'leaderboardentry' by SQLModel default)
    leaderboard_result = session.execute(
        text("""
        SELECT le.id, le.course_id, le.total_time_sec, le.created_at,
               c.name as course_name,
               (SELECT COUNT(*) FROM leaderboardentry le2 
                WHERE le2.course_id = le.course_id 
                AND le2.total_time_sec < le.total_time_sec) + 1 as rank
        FROM leaderboardentry le
        JOIN course c ON c.id = le.course_id
        WHERE le.username = :user_name
        ORDER BY le.total_time_sec
        """),
        {"user_name": user_name}
    )

    leaderboard_positions = []
    for row in leaderboard_result:
        leaderboard_positions.append({
            "id": row.id,
            "courseId": row.course_id,
            "courseName": row.course_name,
            "rank": row.rank,
            "time": row.total_time_sec,
            "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        })

    return JSONResponse({
        "createdCourses": created_courses,
        "leaderboardPositions": leaderboard_positions
    })
