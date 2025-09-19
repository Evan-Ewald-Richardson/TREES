"""User profile and maintenance endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ...core import SUPER_USER_NAME, get_session
from ...models import Course, LeaderboardEntry, User
from ...services.courses import course_to_dict

router = APIRouter(tags=["users"])


def _is_super(user_name: str) -> bool:
    return bool(user_name) and user_name == SUPER_USER_NAME


@router.post("/users/login")
def login_user(body: Dict[str, Any], session: Session = Depends(get_session)):
    """Login or register a user by name."""

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    if len(name) > 40:
        raise HTTPException(400, "Name must be 40 characters or less")

    user = session.exec(select(User).where(User.name == name)).first()
    if not user:
        user = User(name=name)
        session.add(user)
        session.commit()
        session.refresh(user)

    return {
        "id": user.id,
        "name": user.name,
        "created_at": user.created_at.isoformat() + "Z",
    }


@router.get("/users/{user_name}/profile")
def get_user_profile(user_name: str, session: Session = Depends(get_session)):
    """Get user profile with leaderboard positions and created courses."""

    user = session.exec(select(User).where(User.name == user_name)).first()
    if not user:
        raise HTTPException(404, "User not found")

    leaderboard_entries = session.exec(
        select(LeaderboardEntry)
        .where(LeaderboardEntry.username == user_name)
        .order_by(LeaderboardEntry.total_time_sec)
    ).all()

    leaderboard_positions: List[Dict[str, Any]] = []
    for entry in leaderboard_entries:
        course = session.get(Course, entry.course_id)
        if not course:
            continue
        better_entries = session.exec(
            select(LeaderboardEntry)
            .where(LeaderboardEntry.course_id == entry.course_id)
            .where(LeaderboardEntry.total_time_sec < entry.total_time_sec)
        ).all()
        rank = len(better_entries) + 1
        leaderboard_positions.append(
            {
                "id": entry.id,
                "courseId": course.id,
                "courseName": course.name,
                "rank": rank,
                "time": entry.total_time_sec,
                "created_at": entry.created_at.isoformat() + "Z",
            }
        )

    created_courses = session.exec(
        select(Course).where(Course.created_by == user_name).order_by(Course.id.desc())
    ).all()

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "created_at": user.created_at.isoformat() + "Z",
        },
        "leaderboardPositions": leaderboard_positions,
        "createdCourses": [course_to_dict(course) for course in created_courses],
    }


@router.delete("/users/{user_name}/leaderboard/{entry_id}")
def delete_user_leaderboard_entry(
    user_name: str, entry_id: int, session: Session = Depends(get_session)
):
    """Delete a user's leaderboard entry."""

    user = session.exec(select(User).where(User.name == user_name)).first()
    if not user:
        raise HTTPException(404, "User not found")

    entry = session.get(LeaderboardEntry, entry_id)
    if not entry:
        raise HTTPException(404, "Leaderboard entry not found")

    if entry.username != user_name and not _is_super(user_name):
        raise HTTPException(403, "Cannot delete another user's entry")

    session.delete(entry)
    session.commit()
    return {"ok": True, "deleted_entry": entry_id}


@router.delete("/users/{user_name}/courses/{course_id}")
def delete_user_course(
    user_name: str, course_id: int, session: Session = Depends(get_session)
):
    """Delete a user's course along with its leaderboard entries."""

    user = session.exec(select(User).where(User.name == user_name)).first()
    if not user:
        raise HTTPException(404, "User not found")

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    if course.created_by != user_name and not _is_super(user_name):
        raise HTTPException(403, "Cannot delete another user's course")

    entries = session.exec(
        select(LeaderboardEntry).where(LeaderboardEntry.course_id == course_id)
    ).all()
    for entry in entries:
        session.delete(entry)

    session.delete(course)
    session.commit()

    return {"ok": True, "deleted_course": course_id, "deleted_entries": len(entries)}


__all__ = ["router"]
