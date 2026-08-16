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

from datetime import date, datetime, time, timezone


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Local calendar day -> naive-UTC instant bounds. Naive (not
    timezone-aware) because SQLite/SQLAlchemy returns DateTime columns
    as naive datetimes representing UTC on read, so these bounds are
    stripped of tzinfo to compare cleanly against them in Python."""

    local_start = datetime.combine(day, time.min).astimezone()
    local_end = datetime.combine(day, time.max).astimezone()
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )
