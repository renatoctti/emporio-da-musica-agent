from datetime import datetime

import pytest

from emporio.hours import STORE_HOURS, add_business_hours, is_open, next_opening


def dt(day, hour, minute=0):
    """March 2026: the 23rd is a Monday, the 28th a Saturday, the 29th a Sunday."""
    return datetime(2026, 3, day, hour, minute)


def test_store_hours_cover_the_week():
    assert sorted(STORE_HOURS) == [0, 1, 2, 3, 4, 5, 6]
    assert STORE_HOURS[6] is None


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (dt(23, 8, 59), False),
        (dt(23, 9), True),
        (dt(23, 17, 59), True),
        (dt(23, 18), False),
        (dt(28, 12, 59), True),
        (dt(28, 13), False),
        (dt(29, 10), False),
    ],
)
def test_is_open(moment, expected):
    assert is_open(moment) is expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (dt(29, 10), dt(30, 9)),
        (dt(28, 13), dt(30, 9)),
        (dt(23, 8), dt(23, 9)),
        (dt(23, 18), dt(24, 9)),
        (dt(23, 10), dt(23, 10)),
    ],
)
def test_next_opening(moment, expected):
    assert next_opening(moment) == expected


@pytest.mark.parametrize(
    ("start", "hours", "expected"),
    [
        (dt(23, 10), 24, dt(25, 16)),
        (dt(27, 17), 2, dt(28, 10)),
        (dt(28, 12), 24, datetime(2026, 4, 1, 14, 0)),
        (dt(29, 15), 1, dt(30, 10)),
        (dt(29, 15), 24, datetime(2026, 4, 1, 15, 0)),
        (dt(23, 10), 0, dt(23, 10)),
        (dt(23, 10), 0.5, dt(23, 10, 30)),
        (dt(23, 10), 8, dt(23, 18)),
    ],
)
def test_add_business_hours(start, hours, expected):
    assert add_business_hours(start, hours) == expected
