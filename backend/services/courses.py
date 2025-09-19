"""Helpers for course domain objects."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..models import Course


def gates_from_course(course: Course) -> List[Dict[str, Any]]:
    """Extract gates list from stored JSON."""

    return json.loads(course.gates_json or "[]")


def course_to_dict(course: Course) -> Dict[str, Any]:
    """Serialise a course model to API-friendly dict."""

    gates = gates_from_course(course)
    return {
        "id": course.id,
        "name": course.name,
        "buffer_m": course.buffer_m,
        "gates": gates,
        "gate_count": len(gates),
        "created_by": course.created_by,
        "description": course.description,
        "image_url": course.image_url,
        "created_at": course.created_at.isoformat() if course.created_at else None,
    }


__all__ = ["course_to_dict", "gates_from_course"]
