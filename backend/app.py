"""
GPX Leaderboard API
Main FastAPI application for GPX track analysis and leaderboard management.
"""

from __future__ import annotations

import os
import json
import math
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import gpxpy
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Body, status, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import Field as ORMField, SQLModel, Session, select
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from starlette.responses import FileResponse, Response, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from .strava import router as strava_router
from .db_core import engine, get_session
from .settings import SECRET_KEY, FRONTEND_ORIGIN

# Load environment variables
load_dotenv(find_dotenv(), override=False)

# DB Reset toggle
DB_RESET = os.getenv("DB_RESET", "0").lower() in ("1","true","yes")

# Upload directory setup
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name, str(default)).lower()
    return v in ("1", "true", "yes")

# --- Super user for username-only demo auth ---
SUPER_USER_NAME = os.getenv("SUPER_USER_NAME", "EVERGREEN")  # set in env for prod
BACKEND_URL = os.getenv("BACKEND_URL", "")  # Optional backend URL for frontend config
def is_super(user_name: str) -> bool:
    return bool(user_name) and user_name == SUPER_USER_NAME

# OAuth and cookie configuration
from .settings import SECRET_KEY, FRONTEND_ORIGIN
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")  # 'lax' | 'none' | 'strict'
# =============================================================================
# Database Models
# =============================================================================

class Course(SQLModel, table=True):
    id: Optional[int] = ORMField(default=None, primary_key=True)
    name: str
    buffer_m: int = 10
    gates_json: str
    created_by: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    created_at: datetime = ORMField(default_factory=datetime.now(timezone.utc))


class User(SQLModel, table=True):
	"""User model for basic authentication."""
	id: Optional[int] = ORMField(default=None, primary_key=True)
	name: str = ORMField(index=True, unique=True)
	created_at: datetime = ORMField(default_factory=datetime.now(timezone.utc))


class LeaderboardEntry(SQLModel, table=True):
	"""Leaderboard entry model for storing race results."""
	id: Optional[int] = ORMField(default=None, primary_key=True)
	course_id: int = ORMField(index=True)
	username: str
	total_time_sec: int
	segment_times_json: str  # JSON: [{"segment":"Pair 1","timeSec":123}, ...]
	created_at: datetime = ORMField(default_factory=datetime.now(timezone.utc))

# =============================================================================
# Application Lifespan
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    if DB_RESET:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(title="GPX Leaderboard API", version="0.2.0", lifespan=lifespan)

# Configure allowed origins for CORS
allowed_origins_list = []
if FRONTEND_ORIGIN:
	# Handle multiple origins if comma-separated
	origins_from_env = [o.strip() for o in FRONTEND_ORIGIN.split(',') if o.strip()]
	allowed_origins_list.extend(origins_from_env)

# Always allow localhost for local development
if "http://localhost:3000" not in allowed_origins_list:
	allowed_origins_list.append("http://localhost:3000")

# Add Azure default SWA development origin
if "https://nice-water-01234.azurestaticapps.net" not in allowed_origins_list:
	allowed_origins_list.append("https://nice-water-01234.azurestaticapps.net")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET","POST","PATCH","DELETE","OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="sid",
    https_only=COOKIE_SECURE,
    same_site=COOKIE_SAMESITE,
    domain=COOKIE_DOMAIN,
)

app.include_router(strava_router)

# Include OAuth router
from .routers.auth import router as auth_router
app.include_router(auth_router, prefix="")

@app.get("/health")
def health():
	"""Health check endpoint."""
	return {"ok": True}

@app.get("/healthz")
def healthz():
	return JSONResponse({"ok": True})


@app.get("/config")
def get_config():
	"""Get frontend configuration."""
	return {
		"backend_url": BACKEND_URL,
		"super_user_name": SUPER_USER_NAME,
	}


@app.get("/_debug/cors")
def debug_cors(request: Request):
	"""Debug CORS headers for troubleshooting."""
	return {
		"seen_origin": request.headers.get("origin"),
		"acr_method": request.headers.get("access-control-request-method"),
		"acr_headers": request.headers.get("access-control-request-headers"),
	}

# =============================================================================
# GPX Parsing & Upload
# =============================================================================


def parse_gpx_to_tracks(text: str) -> List[Dict[str, Any]]:
	"""
	Parse GPX text and extract track/route data.
	
	Prefer tracks (trk/trkseg/trkpt), fall back to routes (rte/rtept).
	Returns: [{"name": str, "points": [{"lat","lon","ele","time"}]}]
	"""
	gpx = gpxpy.parse(text)
	tracks_out: List[Dict[str, Any]] = []

	# Process tracks
	if gpx.tracks:
		for ti, trk in enumerate(gpx.tracks):
			name = trk.name or f"Track {ti + 1}"
			pts: List[Dict[str, Any]] = []
			for seg in trk.segments or []:
				for p in seg.points or []:
					pts.append({
						"lat": p.latitude,
						"lon": p.longitude,
						"ele": p.elevation if p.elevation is not None else None,
						"time": p.time.isoformat() if p.time else None,
					})
			if pts:
				tracks_out.append({"name": name, "points": pts})

	# Fallback to routes
	if not tracks_out and gpx.routes:
		for ri, rte in enumerate(gpx.routes):
			name = rte.name or f"Route {ri + 1}"
			pts: List[Dict[str, Any]] = []
			for p in rte.points or []:
				pts.append({
					"lat": p.latitude,
					"lon": p.longitude,
					"ele": p.elevation if p.elevation is not None else None,
					"time": p.time.isoformat() if p.time else None,
				})
			if pts:
				tracks_out.append({"name": name, "points": pts})

	return tracks_out


@app.post("/upload-gpx")
async def upload_gpx(gpxfile: UploadFile = File(...)):
	"""Upload and parse GPX file."""
	# Validate file extension and content type
	filename = (gpxfile.filename or "").lower()
	if not (
		filename.endswith(".gpx")
		or gpxfile.content_type in ("application/gpx+xml", "application/xml", "text/xml")
	):
		raise HTTPException(status_code=400, detail="Only GPX files are allowed")

	content = await gpxfile.read()
	if not content.strip():
		raise HTTPException(status_code=400, detail="File is empty")
	if len(content) > 10 * 1024 * 1024:  # 10 MB
		raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

	try:
		text = content.decode("utf-8", errors="ignore")
		tracks = parse_gpx_to_tracks(text)
		if not tracks:
			raise HTTPException(status_code=400, detail="No valid tracks or routes found in GPX file")
		return {"tracks": tracks}
	except HTTPException:
		raise
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to process GPX file: {e}")


# =============================================================================
# Timing Utilities
# =============================================================================


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	"""Calculate distance between two points using Haversine formula."""
	R = 6371000.0  # Earth radius in meters
	dLat = math.radians(lat2 - lat1)
	dLon = math.radians(lon2 - lon1)
	a = math.sin(dLat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2) ** 2
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
	return R * c


def points_near_with_time(points: List[Dict[str, Any]], target: Dict[str, float], radius_m: int):
	"""Find points within radius that have valid timestamps."""
	hits = []
	for idx, p in enumerate(points):
		t = p.get("time")
		if not t:
			continue
		try:
			# Handle ISO format with or without 'Z' and ensure timezone info
			t_dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
			t_ms = t_dt.timestamp() * 1000
		except Exception:
			continue
		if haversine_m(p["lat"], p["lon"], target["lat"], target["lon"]) <= radius_m:
			hits.append({"index": idx, "tMs": t_ms})
	return hits

def point_within_radius(p: Dict[str, Any], target: Dict[str, float], radius_m: int) -> bool:
    return haversine_m(p["lat"], p["lon"], target["lat"], target["lon"]) <= radius_m

def pass_through_target_between(points: List[Dict[str, Any]], target: Dict[str, float], i_start: int, i_end: int, radius_m: int) -> bool:
    for i in range(i_start, i_end + 1):
        if point_within_radius(points[i], target, radius_m):
            return True
    return False


def checkpoints_valid_between(points: List[Dict[str, Any]], checkpoints: List[Dict[str, float]], i_start: int, i_end: int, radius_m: int) -> bool:
    if not checkpoints:
        return True
    for cp in checkpoints:
        if not pass_through_target_between(points, cp, i_start, i_end, radius_m):
            return False
    return True


def compute_segment_times(points: List[Dict[str, Any]], gates: List[Dict[str, Any]], buffer_m: int):
	"""
	Compute segment times for given points and gates.
	
	Args:
		gates: [{"pairId","name","start":{"lat","lon"},"end":{"lat","lon"}}]
		
	Returns:
		[{"segment": name, "timeSec": int|'N/A'}, ...]
	"""
	out: List[Dict[str, Any]] = []
	for g in gates:
		name = g.get("name") or f"Pair {g['pairId']}"
		checkpoints = g.get("checkpoints") or []

		starts = points_near_with_time(points, g["start"], buffer_m)
		ends   = points_near_with_time(points, g["end"],   buffer_m)

		if not starts or not ends:
			out.append({"segment": name, "timeSec": "N/A", "valid": False})
			continue

		best_dt = math.inf
		best_pair = None  # (s_index, e_index)

		for s in starts:
			sidx = s["index"]
			s_ms = s["tMs"]
			for e in ends:
				eidx = e["index"]
				if eidx <= sidx:
					continue
				dt = (e["tMs"] - s_ms) / 1000.0
				if dt > 0 and dt < best_dt:
					best_dt = dt
					best_pair = (sidx, eidx)

		if best_pair is None:
			out.append({"segment": name, "timeSec": "N/A", "valid": False})
			continue

		sidx, eidx = best_pair
		is_valid = checkpoints_valid_between(points, checkpoints, sidx, eidx, buffer_m)

		time_out = int(round(best_dt))
		out.append({"segment": name, "timeSec": time_out, "valid": is_valid})

	return out


# =============================================================================
# Course Helpers
# =============================================================================


def gates_from_course(c: Course) -> List[Dict[str, Any]]:
	"""Extract gates from course JSON."""
	return json.loads(c.gates_json)


def course_to_dict(c: Course) -> Dict[str, Any]:
	"""Convert course to dictionary format."""
	gates = json.loads(c.gates_json or "[]")
	return {
		"id": c.id,
		"name": c.name,
		"buffer_m": c.buffer_m,
		"gates": gates,
		"created_by": c.created_by,
		"description": c.description,
		"image_url": c.image_url,
		"created_at": c.created_at.isoformat() if c.created_at else None,
	}


# =============================================================================
# Course Endpoints
# =============================================================================


@app.post("/courses")
def create_course(body: Dict[str, Any], session: Session = Depends(get_session)):
	"""Create a new course with gate pairs."""
	name = body.get("name")
	buffer_m = int(body.get("buffer_m") or 10)
	gates = body.get("gates") or []
	created_by = body.get("created_by")
	description = body.get("description")  # NEW
	image_url = body.get("image_url")      # NEW (usually None until upload)

	if not name or not isinstance(gates, list) or not gates:
		raise HTTPException(status_code=400, detail="Name and at least one gate are required")

	# Validate gate pair structure
	for g in gates:
		if not {"pairId", "start", "end"} <= set(g.keys()):
			raise HTTPException(400, "Invalid gate pair payload")
		if "checkpoints" in g:
			cps = g["checkpoints"]
			if not isinstance(cps, list) or any(not {"lat", "lon"} <= set(cp.keys()) for cp in cps):
				raise HTTPException(400, "Invalid checkpoints payload")

	c = Course(
		name=name,
		buffer_m=buffer_m,
		gates_json=json.dumps(gates),
		created_by=created_by,
		description=description,
		image_url=image_url,
	)
	session.add(c)
	session.commit()
	session.refresh(c)
	return course_to_dict(c)


@app.get("/courses")
def list_courses(session: Session = Depends(get_session)):
	"""List all courses."""
	cs = session.exec(select(Course)).all()
	return [course_to_dict(c) for c in cs]


@app.get("/courses/{course_id}")
def get_course(course_id: int, session: Session = Depends(get_session)):
	"""Get a specific course by ID."""
	c = session.get(Course, course_id)
	if not c:
		raise HTTPException(404, "Course not found")
	return course_to_dict(c)


@app.delete("/courses/{course_id}")
def delete_course(course_id: int, session: Session = Depends(get_session)):
	"""Delete a course by ID."""
	c = session.get(Course, course_id)
	if not c:
		raise HTTPException(404, "Course not found")
	session.delete(c)
	session.commit()
	return {"ok": True}


# =============================================================================
# User Authentication Endpoints
# =============================================================================


@app.post("/users/login")
def login_user(body: Dict[str, Any], session: Session = Depends(get_session)):
	"""Login or register a user by name."""
	name = (body.get("name") or "").strip()
	if not name:
		raise HTTPException(400, "Name is required")
	
	if len(name) > 40:
		raise HTTPException(400, "Name must be 40 characters or less")
	
	# Check if user exists
	user = session.exec(select(User).where(User.name == name)).first()
	
	if not user:
		# Create new user
		user = User(name=name)
		session.add(user)
		session.commit()
		session.refresh(user)
	
	return {
		"id": user.id,
		"name": user.name,
		"created_at": user.created_at.isoformat() + "Z"
	}


@app.get("/users/{user_name}/profile")
def get_user_profile(user_name: str, session: Session = Depends(get_session)):
	"""Get user profile with leaderboard positions and created courses."""
	user = session.exec(select(User).where(User.name == user_name)).first()
	if not user:
		raise HTTPException(404, "User not found")
	
	# Get user's leaderboard positions across all courses
	leaderboard_entries = session.exec(
		select(LeaderboardEntry).where(LeaderboardEntry.username == user_name)
		.order_by(LeaderboardEntry.total_time_sec)
	).all()
	
	leaderboard_positions = []
	for entry in leaderboard_entries:
		# Get course info
		course = session.get(Course, entry.course_id)
		if course:
			# Calculate rank for this course
			better_entries = session.exec(
				select(LeaderboardEntry)
				.where(LeaderboardEntry.course_id == entry.course_id)
				.where(LeaderboardEntry.total_time_sec < entry.total_time_sec)
			).all()
			rank = len(better_entries) + 1
			
			leaderboard_positions.append({
				"id": entry.id,
				"courseId": course.id,
				"courseName": course.name,
				"rank": rank,
				"time": entry.total_time_sec,
				"created_at": entry.created_at.isoformat() + "Z"
			})
	
	# Get user's created courses
	created_courses = session.exec(
		select(Course).where(Course.created_by == user_name)
		.order_by(Course.id.desc())
	).all()
	
	courses_data = [course_to_dict(c) for c in created_courses]
	
	return {
		"user": {
			"id": user.id,
			"name": user.name,
			"created_at": user.created_at.isoformat() + "Z"
		},
		"leaderboardPositions": leaderboard_positions,
		"createdCourses": courses_data
	}


@app.delete("/users/{user_name}/leaderboard/{entry_id}")
def delete_user_leaderboard_entry(user_name: str, entry_id: int, session: Session = Depends(get_session)):
	"""Delete a user's leaderboard entry."""
	# Verify user exists
	user = session.exec(select(User).where(User.name == user_name)).first()
	if not user:
		raise HTTPException(404, "User not found")
	
	# Get and verify entry belongs to user
	entry = session.get(LeaderboardEntry, entry_id)
	if not entry:
		raise HTTPException(404, "Leaderboard entry not found")
	
	if entry.username != user_name and not is_super(user_name):
		raise HTTPException(403, "Cannot delete another user's entry")
	
	session.delete(entry)
	session.commit()
	return {"ok": True, "deleted_entry": entry_id}


@app.delete("/users/{user_name}/courses/{course_id}")
def delete_user_course(user_name: str, course_id: int, session: Session = Depends(get_session)):
	"""Delete a user's course."""
	# Verify user exists
	user = session.exec(select(User).where(User.name == user_name)).first()
	if not user:
		raise HTTPException(404, "User not found")
	
	# Get and verify course belongs to user
	course = session.get(Course, course_id)
	if not course:
		raise HTTPException(404, "Course not found")
	
	if course.created_by != user_name and not is_super(user_name):
		raise HTTPException(403, "Cannot delete another user's course")
	
	# Delete all leaderboard entries for this course first
	entries = session.exec(
		select(LeaderboardEntry).where(LeaderboardEntry.course_id == course_id)
	).all()
	for entry in entries:
		session.delete(entry)
	
	# Delete the course
	session.delete(course)
	session.commit()
	
	return {"ok": True, "deleted_course": course_id, "deleted_entries": len(entries)}


# =============================================================================
# Leaderboard Endpoints
# =============================================================================


@app.post("/leaderboard/{course_id}/submit")
def submit_result(course_id: int, body: Dict[str, Any], session: Session = Depends(get_session)):
	"""Submit a track result to the leaderboard."""
	c = session.get(Course, course_id)
	if not c:
		raise HTTPException(404, "Course not found")

	username = (body.get("username") or "").strip()
	points = body.get("points") or []
	if not username:
		raise HTTPException(400, "Username required")
	if not points:
		raise HTTPException(400, "No track points provided")

	segs = compute_segment_times(points, gates_from_course(c), c.buffer_m)
	if any(s["timeSec"] == "N/A" for s in segs):
		raise HTTPException(400, "Track does not complete the course (N/A present).")

	total = sum(int(s["timeSec"]) for s in segs)
	
	# Check for existing entry for this user on this course
	existing_entry = session.exec(
		select(LeaderboardEntry).where(
			LeaderboardEntry.course_id == course_id,
			LeaderboardEntry.username == username[:40]
		)
	).first()
	
	if existing_entry:
		# Update only if new time is better (faster)
		if int(total) < existing_entry.total_time_sec:
			existing_entry.total_time_sec = int(total)
			existing_entry.segment_times_json = json.dumps(segs)
			existing_entry.created_at = datetime.now(timezone.utc)()  # Update timestamp for new record
			session.add(existing_entry)
			session.commit()
			session.refresh(existing_entry)
			entry = existing_entry
		else:
			# Return existing entry if new time is not better
			entry = existing_entry
	else:
		# Create new entry if none exists
		entry = LeaderboardEntry(
			course_id=course_id,
			username=username[:40],
			total_time_sec=int(total),
			segment_times_json=json.dumps(segs),
		)
		session.add(entry)
		session.commit()
		session.refresh(entry)

	return {
		"ok": True,
		"entry_id": entry.id,
		"total_time_sec": entry.total_time_sec,
		"segments": segs,
	}


@app.get("/leaderboard/{course_id}")
def get_leaderboard(course_id: int, session: Session = Depends(get_session), limit: int = 50):
	"""Get leaderboard entries for a course."""
	c = session.get(Course, course_id)
	if not c:
		raise HTTPException(404, "Course not found")

	q = (
		session.exec(
			select(LeaderboardEntry)
			.where(LeaderboardEntry.course_id == course_id)
			.order_by(LeaderboardEntry.total_time_sec)
			.limit(limit)
		)
		.all()
	)

	out = []
	for e in q:
		out.append({
			"id": e.id,
			"username": e.username,
			"total_time_sec": e.total_time_sec,
			"segments": json.loads(e.segment_times_json),
			"created_at": e.created_at.isoformat() + "Z",
		})
	return {"course_id": course_id, "entries": out}


@app.post("/segment-times")
def segment_times(payload: Dict[str, Any] = Body(...)):
	"""
	Compute segment times for given points and gates.
	
	Request:
		{
			"points": [{lat, lon, ele?, time?}, ...],
			"gates":  [{"pairId","name","start":{"lat","lon"},"end":{"lat","lon"}}, ...],
			"buffer_m": 10
		}
		
	Response:
		{ "segments": [{"segment":"Pair 1","timeSec":123}|{"segment":"Pair 1","timeSec":"N/A"}, ...] }
	"""
	points = payload.get("points") or []
	gates = payload.get("gates") or []
	buffer_m = int(payload.get("buffer_m") or 10)
	if not gates:
		return {"segments": []}
	segs = compute_segment_times(points, gates, buffer_m)
	return {"segments": segs}


# =============================================================================
# Course Image Upload
# =============================================================================

@app.post("/courses/{course_id}/image")
async def upload_course_image(course_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)):
	"""Upload an image for a course."""
	c = session.get(Course, course_id)
	if not c:
		raise HTTPException(404, "Course not found")

	ext = (os.path.splitext(file.filename or "")[1] or ".jpg").lower()
	if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
		raise HTTPException(400, "Unsupported image type")

	fname = f"course_{course_id}{ext}"
	dest = UPLOAD_DIR / fname
	data = await file.read()
	dest.write_bytes(data)

	# Expose via static route (below) or your CDN
	c.image_url = f"/uploads/{fname}"
	session.add(c)
	session.commit()
	session.refresh(c)
	return {"ok": True, "image_url": c.image_url}


@app.get("/uploads/{path}")
def serve_upload(path: str):
	"""Serve uploaded files."""
	file_path = UPLOAD_DIR / path
	if not file_path.exists():
		raise HTTPException(404, "File not found")
	return FileResponse(file_path)


@app.get("/courses_summary")
def courses_summary(session: Session = Depends(get_session)):
	"""Get courses with first place leaderboard data."""
	courses = session.exec(select(Course)).all()
	out = []
	for c in courses:
		winner = session.exec(
			select(LeaderboardEntry)
			.where(LeaderboardEntry.course_id == c.id)
			.order_by(LeaderboardEntry.total_time_sec.asc())
			.limit(1)
		).first()
		out.append({
			**course_to_dict(c),
			"first_place": (
				{"username": winner.username, "total_time_sec": winner.total_time_sec}
				if winner else None
			)
		})
	return out


# =============================================================================
# Development Entrypoint
# =============================================================================

if __name__ == "__main__":
	import uvicorn
	
	# Use an import string to avoid the "must pass application as an import string" warning
	uvicorn.run("app:app", host="127.0.0.1", port=3000, reload=True)