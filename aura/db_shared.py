"""Date/time functions for the database modules; stable public re-exports."""
from __future__ import annotations
import calendar
from datetime import datetime, timezone

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def months_before(months: int, date: datetime | None = None) -> str:
    """Rolling calendar-month window, not an imprecise 30*months days."""
    date = (date or datetime.now(timezone.utc)).astimezone(timezone.utc)
    month_index = date.year * 12 + (date.month - 1) - months
    year, index = divmod(month_index, 12)
    day = min(date.day, calendar.monthrange(year, index + 1)[1])
    return date.replace(year=year, month=index+1, day=day).isoformat(timespec='seconds')
