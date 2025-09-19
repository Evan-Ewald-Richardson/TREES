"""Course management endpoints."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, func, select

from ...core import UPLOAD_DIR, get_session
from ...models import Course, LeaderboardEntry
from ...services.courses import course_to_dict

router = APIRouter(tags=["courses"])


def _validate_gates(gates: List[Dict[str, Any]]) -> None:
    for gate in gates:
        if not {"pairId", "start", "end"} <= set(gate.keys()):
            raise HTTPException(400, "Invalid gate pair payload")
        if "checkpoints" in gate:
            checkpoints = gate["checkpoints"]
            if not isinstance(checkpoints, list) or any(
                not {"lat", "lon"} <= set(cp.keys()) for cp in checkpoints
            ):
                raise HTTPException(400, "Invalid checkpoints payload")


@router.post("/courses")
def create_course(body: Dict[str, Any], session: Session = Depends(get_session)):
    """Create a new course with gate pairs."""

    name = body.get("name")
    buffer_m = int(body.get("buffer_m") or 10)
    gates = body.get("gates") or []
    created_by = body.get("created_by")
    description = body.get("description")
    image_url = body.get("image_url")

    if not name or not isinstance(gates, list) or not gates:
        raise HTTPException(status_code=400, detail="Name and at least one gate are required")

    _validate_gates(gates)

    course = Course(
        name=name,
        buffer_m=buffer_m,
        gates_json=json.dumps(gates),
        created_by=created_by,
        description=description,
        image_url=image_url,
    )
    session.add(course)
    session.commit()
    session.refresh(course)
    return course_to_dict(course)


@router.get("/courses")
def list_courses(session: Session = Depends(get_session)):
    """List all courses."""

    courses = session.exec(select(Course)).all()
    return [course_to_dict(course) for course in courses]


@router.get("/courses/{course_id}")
def get_course(course_id: int, session: Session = Depends(get_session)):
    """Get a specific course by ID."""

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    return course_to_dict(course)


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, session: Session = Depends(get_session)):
    """Delete a course by ID."""

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    session.delete(course)
    session.commit()
    return {"ok": True}


@router.post("/courses/{course_id}/image")
async def upload_course_image(
    course_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Upload an image for a course."""

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    ext = (os.path.splitext(file.filename or "")[1] or ".jpg").lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(400, "Unsupported image type")

    filename = f"course_{course_id}{ext}"
    destination = UPLOAD_DIR / filename
    data = await file.read()
    destination.write_bytes(data)

    course.image_url = f"/uploads/{filename}"
    session.add(course)
    session.commit()
    session.refresh(course)
    return {"ok": True, "image_url": course.image_url}


@router.get("/courses_summary")
def courses_summary(session: Session = Depends(get_session)):
    """Get courses with first place leaderboard data."""

    courses = session.exec(select(Course)).all()
    summary = []
    for course in courses:
        leaderboard_count = session.exec(
            select(func.count(LeaderboardEntry.id)).where(
                LeaderboardEntry.course_id == course.id
            )
        ).one()

        winner = session.exec(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.course_id == course.id)
            .order_by(LeaderboardEntry.total_time_sec.asc())
            .limit(1)
        ).first()

        summary.append(
            {
                **course_to_dict(course),
                "leaderboard_count": leaderboard_count,
                "first_place": (
                    {
                        "username": winner.username,
                        "total_time_sec": winner.total_time_sec,
                    }
                    if winner
                    else None
                ),
            }
        )
    return summary


@router.get("/uploads/{path}")
def serve_upload(path: str):
    """Serve uploaded files."""

    file_path = UPLOAD_DIR / path
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(file_path)


__all__ = ["router"]
