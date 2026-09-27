"""Shared validation for forecast, export and event date ranges."""
from datetime import date

from fastapi import HTTPException


def date_range(start: date | None, end: date | None) -> tuple[str | None, str | None]:
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    return start.isoformat() if start else None, end.isoformat() if end else None
