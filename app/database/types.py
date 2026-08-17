"""Custom SQLAlchemy column types.

UtcDateTime exists because SQLite has no native datetime type at all
(concept: type affinity - there are only five storage classes, NULL,
INTEGER, REAL, TEXT and BLOB). SQLAlchemy's SQLite dialect therefore
stores a DateTime as an ISO-8601 *string*, and a string carries no
timezone offset unless one is written into it. The value written is the
correct UTC instant; what is lost on the round trip is the tzinfo label
saying so.

The consequence is that every value read back is NAIVE, and comparing a
naive datetime with an aware one - `datetime.now(timezone.utc)`, which is
what the rest of this app correctly uses - raises TypeError. Worse, when
a comparison happens to succeed (both sides naive), it succeeds against
a *local* wall-clock reading being compared to a UTC one, which is
silently wrong by the machine's UTC offset. This dev machine runs IST,
UTC+5:30, and that is exactly how the shipped fuel-reconciliation bug
happened: a naive local day boundary compared against UTC-stored
transaction timestamps silently dropped every transaction recorded
between local midnight and 05:30 UTC.

That bug was fixed at two call sites (app/core/dates.py's
local_day_bounds_utc, and AuditLogRepository.search) and worked around at
a third (_as_aware_utc in auth_service.py). The trap stayed armed at
every other one, because it lived in the column type rather than in any
particular query.

This type disarms it structurally: it normalises to UTC on the way in and
re-attaches timezone.utc on the way out, so a value read from the
database is always aware and always comparable. It cannot be forgotten at
a new call site, which is the whole point - the previous state of affairs
required every author to remember.

No data migration is needed. The bytes already on disk are correct UTC
instants; only the label was missing, and this supplies it on read.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A DateTime that is always timezone-aware UTC in Python."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        """Going in: everything is normalised to UTC, then stored naive.

        Stored naive because that is what SQLite does anyway, and keeping
        the on-disk format byte-identical to what previous versions wrote
        is what makes this change need no migration and stay compatible
        with every existing database in the field.
        """
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            # A naive value reaching this point is a bug in the caller,
            # but assuming UTC matches what the app has always done and
            # is strictly better than storing a local reading unlabelled.
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        """Coming out: always aware UTC, so comparisons are meaningful."""
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
