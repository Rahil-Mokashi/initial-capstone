"""Shared date-boundary helpers.

local_day_bounds_utc exists because of a real bug found and fixed
2026-08-16 (see TankTransactionRepository.sum_for_tank_by_type and
DashboardService): a naive local-calendar-day boundary compared
directly against a UTC-stored timestamp silently drops records
recorded after local midnight whenever local time runs ahead of UTC
(e.g. IST, UTC+5:30). Every place that filters a UTC-stored datetime
column by a local calendar date should go through this helper rather
than re-deriving the conversion.
"""

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Local calendar day -> timezone-aware UTC instant bounds.

    These used to be returned NAIVE, with tzinfo deliberately stripped,
    to match the naive datetimes SQLAlchemy handed back from SQLite. That
    was a workaround for a defect in the column type, not a design
    choice: it meant a UTC instant and a value read from the database
    could be compared only because BOTH had lost the information that
    would have made the comparison meaningful.

    app/database/types.py's UtcDateTime fixed the columns, so every
    datetime read from the database is now aware UTC. The workaround has
    to go with it - keeping it would reintroduce exactly the naive-vs-
    aware mismatch it was invented to hide, just in the other direction.
    """

    local_start = datetime.combine(day, time.min).astimezone()
    local_end = datetime.combine(day, time.max).astimezone()
    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


class PeriodType(str, Enum):
    """Reporting period granularity (business performance reports)."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


def period_bounds(period_type: PeriodType, reference_date: date) -> tuple[date, date]:
    """The local calendar date range a period covers, inclusive on both
    ends. WEEK is Monday-Sunday (ISO week) containing reference_date."""

    if period_type == PeriodType.DAY:
        return reference_date, reference_date

    if period_type == PeriodType.WEEK:
        start = reference_date - timedelta(days=reference_date.weekday())
        return start, start + timedelta(days=6)

    if period_type == PeriodType.MONTH:
        start = reference_date.replace(day=1)
        if start.month == 12:
            next_month_start = start.replace(year=start.year + 1, month=1)
        else:
            next_month_start = start.replace(month=start.month + 1)
        return start, next_month_start - timedelta(days=1)

    if period_type == PeriodType.QUARTER:
        quarter_index = (reference_date.month - 1) // 3
        start_month = quarter_index * 3 + 1
        start = reference_date.replace(month=start_month, day=1)
        if start_month == 10:
            next_quarter_start = start.replace(year=start.year + 1, month=1)
        else:
            next_quarter_start = start.replace(month=start_month + 3)
        return start, next_quarter_start - timedelta(days=1)

    if period_type == PeriodType.YEAR:
        return reference_date.replace(month=1, day=1), reference_date.replace(month=12, day=31)

    raise ValueError(f"Unknown period type: {period_type}")


def period_bounds_utc(period_type: PeriodType, reference_date: date) -> tuple[datetime, datetime]:
    """period_bounds, converted to aware-UTC instants via local_day_bounds_utc."""

    start_date, end_date = period_bounds(period_type, reference_date)
    return local_day_bounds_utc(start_date)[0], local_day_bounds_utc(end_date)[1]
