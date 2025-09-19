"""User profile and maintenance endpoints."""

from __future__ import annotations

import uuid

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ...core import SUPER_USER_EMAILS, SUPER_USER_NAME, get_session
from ...models import Course, LeaderboardEntry, OAuthUser, User
from ...services.courses import course_to_dict

router = APIRouter(tags=["users"])


_SUPER_USER_NAME_CANON = (SUPER_USER_NAME or "").strip().lower()
_SUPER_ADMIN_EMAILS = {email.strip().lower() for email in SUPER_USER_EMAILS if email}


def _is_super(
    user_name: str,
    *,
    session: Session,
    request: Request | None = None,
) -> bool:
    normalized = (user_name or "").strip().lower()
    if normalized and normalized == _SUPER_USER_NAME_CANON:
        return True

    if not _SUPER_ADMIN_EMAILS or request is None:
        return False

    role = request.session.get("role")
    if role != "admin":
        return False

    uid = request.session.get("uid")
    if not uid:
        return False

    try:
        user_uuid = uuid.UUID(str(uid))
    except (ValueError, TypeError):
        return False

    oauth_user = session.get(OAuthUser, user_uuid)
    if not oauth_user:
        return False

    email = (oauth_user.email or "").strip().lower()
    return email in _SUPER_ADMIN_EMAILS


def _normalize_user_name(user_name: str) -> str:
    """Normalize inbound user names to match storage rules."""

    normalized = (user_name or "").strip()
    if not normalized:
        raise HTTPException(400, "User name is required")
    return normalized[:40]


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
def get_user_profile(
    user_name: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Get user profile with leaderboard positions and created courses."""

    normalized_name = _normalize_user_name(user_name)
    is_super = _is_super(normalized_name, session=session, request=request)

    user = session.exec(select(User).where(User.name == normalized_name)).first()
    if not user and not is_super:
        raise HTTPException(404, "User not found")

    leaderboard_entries = session.exec(
        select(LeaderboardEntry)
        .where(LeaderboardEntry.username == normalized_name)
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

    courses_query = select(Course).order_by(Course.id.desc())
    if not is_super:
        courses_query = courses_query.where(Course.created_by == normalized_name)
    created_courses = session.exec(courses_query).all()

    user_created_at = (
        user.created_at.isoformat() + "Z"
        if user and user.created_at
        else None
    )

    return {
        "user": {
            "id": user.id if user else None,
            "name": normalized_name,
            "created_at": user_created_at,
        },
        "leaderboardPositions": leaderboard_positions,
        "createdCourses": [course_to_dict(course) for course in created_courses],
        "isAdmin": is_super,
    }


@router.delete("/users/{user_name}/leaderboard/{entry_id}")
def delete_user_leaderboard_entry(
    user_name: str,
    entry_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Delete a user's leaderboard entry."""

    normalized_name = _normalize_user_name(user_name)

    entry = session.get(LeaderboardEntry, entry_id)
    if not entry:
        raise HTTPException(404, "Leaderboard entry not found")

    is_super = _is_super(normalized_name, session=session, request=request)
    if entry.username != normalized_name and not is_super:
        raise HTTPException(403, "Cannot delete another user's entry")

    session.delete(entry)
    session.commit()
    return {"ok": True, "deleted_entry": entry_id}


@router.delete("/users/{user_name}/courses/{course_id}")
def delete_user_course(
    user_name: str,
    course_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Delete a user's course along with its leaderboard entries."""

    normalized_name = _normalize_user_name(user_name)

    course = session.get(Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")

    is_super = _is_super(normalized_name, session=session, request=request)
    if course.created_by != normalized_name and not is_super:
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
