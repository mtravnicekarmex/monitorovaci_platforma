from __future__ import annotations

import calendar
from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday for the given year."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def czech_public_holidays(year: int) -> frozenset[date]:
    easter = easter_sunday(year)
    return frozenset(
        {
            date(year, 1, 1),
            easter - timedelta(days=2),
            easter + timedelta(days=1),
            date(year, 5, 1),
            date(year, 5, 8),
            date(year, 7, 5),
            date(year, 7, 6),
            date(year, 9, 28),
            date(year, 10, 28),
            date(year, 11, 17),
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
        }
    )


def is_czech_business_day(value: date) -> bool:
    return value.weekday() < 5 and value not in czech_public_holidays(value.year)


def last_czech_business_day(year: int, month: int) -> date:
    value = date(year, month, calendar.monthrange(year, month)[1])
    while not is_czech_business_day(value):
        value -= timedelta(days=1)
    return value


def is_last_czech_business_day(value: date) -> bool:
    return value == last_czech_business_day(value.year, value.month)
