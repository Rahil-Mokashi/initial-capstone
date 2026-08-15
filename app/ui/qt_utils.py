"""Small, shared Qt <-> Python type conversion helpers for the UI layer."""

from datetime import date

from PySide6.QtCore import QDate


def qdate_to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


def date_to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)
