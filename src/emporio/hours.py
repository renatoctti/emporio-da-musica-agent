"""Store opening hours (manual item 2) and business-hour arithmetic.

Holidays are ignored (assumption A7): only Sunday is treated as closed.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

_WEEKDAY = (time(9, 0), time(18, 0))
_SATURDAY = (time(9, 0), time(13, 0))

# weekday() -> (opens, closes), or None when closed
STORE_HOURS: dict[int, tuple[time, time] | None] = {
    0: _WEEKDAY,
    1: _WEEKDAY,
    2: _WEEKDAY,
    3: _WEEKDAY,
    4: _WEEKDAY,
    5: _SATURDAY,
    6: None,
}


def is_open(now: datetime) -> bool:
    hours = STORE_HOURS[now.weekday()]
    return hours is not None and hours[0] <= now.time() < hours[1]


def next_opening(now: datetime) -> datetime:
    """`now` itself when the store is open, otherwise the next moment it opens."""
    if is_open(now):
        return now
    for offset in range(8):
        day = now.date() + timedelta(days=offset)
        hours = STORE_HOURS[day.weekday()]
        if hours is None:
            continue
        opening = datetime.combine(day, hours[0])
        if opening >= now:
            return opening
    raise AssertionError("STORE_HOURS has no open day")  # unreachable with the table above


def add_business_hours(start: datetime, hours: float) -> datetime:
    """Move `hours` forward counting only the time the store is open."""
    remaining = timedelta(hours=hours)
    cursor = next_opening(start)
    while True:
        closing_time = STORE_HOURS[cursor.weekday()][1]  # open today, so not None
        closing = datetime.combine(cursor.date(), closing_time)
        available = closing - cursor
        if remaining <= available:
            return cursor + remaining
        remaining -= available
        cursor = next_opening(closing)
