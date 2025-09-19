"""GPX upload and timing endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from ...services.gpx import compute_segment_times, parse_gpx_to_tracks

router = APIRouter(prefix="", tags=["gpx"])


@router.post("/upload-gpx")
async def upload_gpx(gpxfile: UploadFile = File(...)) -> Dict[str, List[Dict[str, Any]]]:
    """Upload and parse a GPX file into track data."""

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
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    try:
        text = content.decode("utf-8", errors="ignore")
        tracks = parse_gpx_to_tracks(text)
        if not tracks:
            raise HTTPException(status_code=400, detail="No valid tracks or routes found in GPX file")
        return {"tracks": tracks}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to process GPX file: {exc}") from exc


@router.post("/segment-times")
def segment_times(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Compute segment times for given points and gates."""

    points = payload.get("points") or []
    gates = payload.get("gates") or []
    buffer_m = int(payload.get("buffer_m") or 10)
    if not gates:
        return {"segments": []}
    segments = compute_segment_times(points, gates, buffer_m)
    return {"segments": segments}


__all__ = ["router"]
