"""Small, shared Qt <-> Python type conversion and error-handling helpers
for the UI layer."""

from datetime import date

from PySide6.QtCore import QDate

from app.core.logging import logger


def qdate_to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


def date_to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def chain_enter_to_next_field(*fields) -> None:
    """Make pressing Enter/Return in each QLineEdit move focus to the
    next field in sequence, instead of Qt's default behavior of
    immediately triggering the dialog's default button - so filling in
    a multi-field form with the keyboard alone (username -> password,
    or any other field-after-field entry) advances one field at a time
    rather than submitting early on the first Enter press.

    Pass the form's fields in visual order, including non-QLineEdit
    widgets (QDateEdit, QComboBox, ...) that sit between text fields -
    only fields with a returnPressed signal act as a source (Qt doesn't
    give every widget one), but any widget can be a target, since
    setFocus() is universal.

    The caller is responsible for connecting the *last* QLineEdit's own
    returnPressed signal to whatever should actually submit the form -
    this only chains the fields before it.
    """
    for current_field, next_field in zip(fields, fields[1:]):
        return_pressed = getattr(current_field, "returnPressed", None)
        if return_pressed is not None:
            return_pressed.connect(next_field.setFocus)


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
