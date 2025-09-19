"""Leaderboard endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ...core import get_session, utcnow
from ...models import Course, LeaderboardEntry
from ...services.courses import gates_from_course
from ...services.gpx import compute_segment_times

router = APIRouter(tags=["leaderboard"])


@router.post("/leaderboard/{course_id}/submit")
def submit_result(
    course_id: int, body: Dict[str, Any], session: Session = Depends(get_session)
):
    """Submit a track result to the leaderboard."""

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    username = (body.get("username") or "").strip()
    points = body.get("points") or []
    if not username:
        raise HTTPException(400, "Username required")
    if not points:
        raise HTTPException(400, "No track points provided")

    segments = compute_segment_times(points, gates_from_course(course), course.buffer_m)
    if any(segment["timeSec"] == "N/A" for segment in segments):
        raise HTTPException(400, "Track does not complete the course (N/A present).")

    total_seconds = sum(int(segment["timeSec"]) for segment in segments)

    existing_entry = session.exec(
        select(LeaderboardEntry).where(
            LeaderboardEntry.course_id == course_id,
            LeaderboardEntry.username == username[:40],
        )
    ).first()

    if existing_entry:
        if int(total_seconds) < existing_entry.total_time_sec:
            existing_entry.total_time_sec = int(total_seconds)
            existing_entry.segment_times_json = json.dumps(segments)
            existing_entry.created_at = utcnow()
            session.add(existing_entry)
            session.commit()
            session.refresh(existing_entry)
            entry = existing_entry
        else:
            entry = existing_entry
    else:
        entry = LeaderboardEntry(
            course_id=course_id,
            username=username[:40],
            total_time_sec=int(total_seconds),
            segment_times_json=json.dumps(segments),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)

    return {
        "ok": True,
        "entry": {
            "id": entry.id,
            "username": entry.username,
            "total_time_sec": entry.total_time_sec,
            "segments": segments,
            "created_at": entry.created_at.isoformat() + "Z",
        },
    }


@router.get("/leaderboard/{course_id}")
def get_leaderboard(course_id: int, session: Session = Depends(get_session)):
    """Get leaderboard entries for a course."""

    entries = session.exec(
        select(LeaderboardEntry)
        .where(LeaderboardEntry.course_id == course_id)
        .order_by(LeaderboardEntry.total_time_sec.asc())
    ).all()

    return {
        "course_id": course_id,
        "entries": [
            {
                "id": entry.id,
                "username": entry.username,
                "total_time_sec": entry.total_time_sec,
                "segments": json.loads(entry.segment_times_json),
                "created_at": entry.created_at.isoformat() + "Z",
            }
            for entry in entries
        ],
    }


__all__ = ["router"]
