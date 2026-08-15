"""Small, shared Qt <-> Python type conversion and error-handling helpers
for the UI layer."""

from datetime import date

from PySide6.QtCore import QDate

from app.core.logging import logger


def qdate_to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


def date_to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


GENERIC_ERROR_MESSAGE = "Something went wrong. Please try again, and contact support if this keeps happening."


def describe_unexpected_error(exc: Exception) -> str:
    """Log the full traceback for diagnosis and return a safe, generic
    message for display.

    Every UI action should catch AppError/ValidationError first for a
    specific, actionable message, then fall back to this for anything
    else (a DB error, a bug, a Qt quirk) so an unexpected exception never
    crashes the app or leaves the user staring at a raw traceback.
    """
    logger.exception("Unexpected error in UI action: %s", exc)
    return GENERIC_ERROR_MESSAGE
