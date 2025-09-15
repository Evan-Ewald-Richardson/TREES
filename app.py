# app.py
from __future__ import annotations

import json
import math
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import gpxpy
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Field as ORMField, SQLModel, Session, create_engine, select

# =============================================================================
# Database (SQLite)
# =============================================================================

engine = create_engine("sqlite:///./app.db", connect_args={"check_same_thread": False})


class Course(SQLModel, table=True):
    id: Optional[int] = ORMField(default=None, primary_key=True)
    name: str
    buffer_m: int = 10
    # JSON string:
    # [{"pairId":1,"name":"Gate Pair 1","start":{"lat":..,"lon":..},"end":{"lat":..,"lon":..}}, ...]
    gates_json: str


class LeaderboardEntry(SQLModel, table=True):
    id: Optional[int] = ORMField(default=None, primary_key=True)
    course_id: int = ORMField(index=True)
    username: str
    total_time_sec: int
    segment_times_json: str  # [{"segment":"Pair 1","timeSec":123}, ...]
    created_at: datetime = ORMField(default_factory=datetime.utcnow)


def get_session():
    with Session(engine) as session:
        yield session


# =============================================================================
# Lifespan (replaces @app.on_event("startup"))
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    SQLModel.metadata.create_all(engine)
    yield
    # Shutdown (nothing specific to clean up for SQLite)


# =============================================================================
# FastAPI app
# =============================================================================

app = FastAPI(title="GPX Leaderboard API", version="0.2.0", lifespan=lifespan)

# CORS (relax for local dev; tighten in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # set to your site origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# GPX parsing & upload
# =============================================================================

def parse_gpx_to_tracks(text: str) -> List[Dict[str, Any]]:
    """
    Mirrors your old Express behavior:
    - Prefer tracks (trk/trkseg/trkpt)
    - If none found, fall back to routes (rte/rtept)
    Returns: [{"name": str, "points": [{"lat","lon","ele","time"}]}]
    """
    gpx = gpxpy.parse(text)
    tracks_out: List[Dict[str, Any]] = []

    # Tracks
    if gpx.tracks:
        for ti, trk in enumerate(gpx.tracks):
            name = trk.name or f"Track {ti + 1}"
            pts: List[Dict[str, Any]] = []
            for seg in trk.segments or []:
                for p in seg.points or []:
                    pts.append(
                        {
                            "lat": p.latitude,
                            "lon": p.longitude,
                            "ele": p.elevation if p.elevation is not None else None,
                            "time": p.time.isoformat() if p.time else None,
                        }
                    )
            if pts:
                tracks_out.append({"name": name, "points": pts})

    # Fallback to routes
    if not tracks_out and gpx.routes:
        for ri, rte in enumerate(gpx.routes):
            name = rte.name or f"Route {ri + 1}"
            pts: List[Dict[str, Any]] = []
            for p in rte.points or []:
                pts.append(
                    {
                        "lat": p.latitude,
                        "lon": p.longitude,
                        "ele": p.elevation if p.elevation is not None else None,
                        "time": p.time.isoformat() if p.time else None,
                    }
                )
            if pts:
                tracks_out.append({"name": name, "points": pts})

    return tracks_out


@app.post("/upload-gpx")
async def upload_gpx(gpxfile: UploadFile = File(...)):
    # Validate extension / content-type (keep parity with your old server)
    filename = (gpxfile.filename or "").lower()
    if not (
        filename.endswith(".gpx")
        or gpxfile.content_type
        in ("application/gpx+xml", "application/xml", "text/xml")
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
# Timing utils (strictly timestamp-based)
# =============================================================================

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0  # meters
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def points_near_with_time(points: List[Dict[str, Any]], target: Dict[str, float], radius_m: int):
    hits = []
    for idx, p in enumerate(points):
        t = p.get("time")
        if not t:
            continue
        try:
            t_ms = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000
        except Exception:
            continue
        if haversine_m(p["lat"], p["lon"], target["lat"], target["lon"]) <= radius_m:
            hits.append({"index": idx, "tMs": t_ms})
    return hits


def compute_segment_times(points: List[Dict[str, Any]], gates: List[Dict[str, Any]], buffer_m: int):
    """
    gates: [{"pairId","name","start":{"lat","lon"},"end":{"lat","lon"}}]
    returns: [{"segment": name, "timeSec": int|'N/A'}, ...]
    """
    out: List[Dict[str, Any]] = []
    for g in gates:
        name = g.get("name") or f"Pair {g['pairId']}"
        starts = points_near_with_time(points, g["start"], buffer_m)
        ends = points_near_with_time(points, g["end"], buffer_m)
        if not starts or not ends:
            out.append({"segment": name, "timeSec": "N/A"})
            continue
        best = math.inf
        for s in starts:
            for e in ends:
                if e["index"] > s["index"]:
                    dt = (e["tMs"] - s["tMs"]) / 1000.0
                    if dt > 0 and dt < best:
                        best = dt
        out.append({"segment": name, "timeSec": "N/A" if best is math.inf else int(round(best))})
    return out


# =============================================================================
# Helpers for Course dicts
# =============================================================================

def gates_from_course(c: Course) -> List[Dict[str, Any]]:
    return json.loads(c.gates_json)


def course_to_dict(c: Course) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "buffer_m": c.buffer_m, "gates": gates_from_course(c)}


# =============================================================================
# Courses endpoints
# =============================================================================

@app.post("/courses")
def create_course(body: Dict[str, Any], session: Session = Depends(get_session)):
    name = (body.get("name") or "").strip()
    buffer_m = int(body.get("buffer_m") or 10)
    gates = body.get("gates") or []

    if not name:
        raise HTTPException(400, "Course name required")
    if not gates:
        raise HTTPException(400, "Course must include at least one gate pair")

    # minimal shape validation
    for g in gates:
        if not {"pairId", "start", "end"} <= set(g.keys()):
            raise HTTPException(400, "Invalid gate pair payload")

    c = Course(name=name, buffer_m=buffer_m, gates_json=json.dumps(gates))
    session.add(c)
    session.commit()
    session.refresh(c)
    return course_to_dict(c)


@app.get("/courses")
def list_courses(session: Session = Depends(get_session)):
    cs = session.exec(select(Course)).all()
    return [course_to_dict(c) for c in cs]


@app.get("/courses/{course_id}")
def get_course(course_id: int, session: Session = Depends(get_session)):
    c = session.get(Course, course_id)
    if not c:
        raise HTTPException(404, "Course not found")
    return course_to_dict(c)


@app.delete("/courses/{course_id}")
def delete_course(course_id: int, session: Session = Depends(get_session)):
    c = session.get(Course, course_id)
    if not c:
        raise HTTPException(404, "Course not found")
    session.delete(c)
    session.commit()
    return {"ok": True}


# =============================================================================
# Leaderboard endpoints
# =============================================================================

@app.post("/leaderboard/{course_id}/submit")
def submit_result(course_id: int, body: Dict[str, Any], session: Session = Depends(get_session)):
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
        out.append(
            {
                "id": e.id,
                "username": e.username,
                "total_time_sec": e.total_time_sec,
                "segments": json.loads(e.segment_times_json),
                "created_at": e.created_at.isoformat() + "Z",
            }
        )
    return {"course_id": course_id, "entries": out}

@app.post("/segment-times")
def segment_times(payload: Dict[str, Any] = Body(...)):
    """
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

# Serve your static frontend from ./public (index.html at /)
app.mount("/", StaticFiles(directory="public", html=True), name="public")

# =============================================================================
# Dev entrypoint
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    # Use an import string to avoid the "must pass application as an import string" warning
    uvicorn.run("app:app", host="127.0.0.1", port=3000, reload=True)
