"""Small, shared Qt <-> Python type conversion and error-handling helpers
for the UI layer."""

from datetime import date

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QWidget

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


def apply_hard_shadow(widget: QWidget, dx: int = 5, dy: int = 5, color: str | None = None) -> None:
    """Give a card-like widget the design system's soft card elevation - a
    gently blurred, low-opacity shadow sitting close under the card, the
    same "shadow-subtle-card" language the second reskin pass (2026-08-25,
    matching the PetrolStream reference) uses everywhere: barely-there
    elevation plus the card's own hairline border does the visual work,
    not a heavy shadow.

    Function/parameter names are kept as-is (`apply_hard_shadow`, `dx`/`dy`)
    even though the shadow itself is no longer hard-edged - every existing
    caller (TankGaugeCard, VarianceBarCard, DashboardCard, StatCard,
    AlertCard, the login card, MyShiftWindow's card, FuelTypeSummaryCard)
    picks up the new softer look automatically with no call-site changes,
    which matters more here than the name staying literally accurate.

    QSS (Qt's stylesheet language) has no `box-shadow` property, so this
    can't be expressed as a selector in styles.py the way colors/borders
    are - it has to be attached in code, per widget, via
    QGraphicsDropShadowEffect.

    `color` defaults to None, meaning "whatever the active theme's shadow
    color is" (light mode's is near-black at low opacity; dark mode needs
    a lighter grey at low opacity, since a black-on-black shadow would be
    invisible) - resolved here rather than at each call site, so every
    existing caller picks up the right color for both themes automatically
    instead of needing to be taught about theming.
    """
    if color is None:
        from app.ui.styles import DARK_SHADOW_COLOR, LIGHT_SHADOW_COLOR
        from app.ui.theme import is_dark_mode

        color = DARK_SHADOW_COLOR if is_dark_mode() else LIGHT_SHADOW_COLOR

    shadow_color = QColor(color)
    shadow_color.setAlpha(46)

    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(28)
    shadow.setOffset(0, max(dx, dy) // 2)
    shadow.setColor(shadow_color)
    widget.setGraphicsEffect(shadow)


def _draw_pencil_icon(size: int = 16) -> QIcon:
    """A small pencil pictogram drawn with QPainter rather than an emoji
    glyph or a bundled icon file - matching the app-wide decision (see
    the 2026-09-01 emoji-removal commit) to drop colorful emoji pictographs
    everywhere, and reusing the exact "draw the icon at call time" approach
    MainWindow._make_avatar already uses for the account badge, so it
    stays a single flat color that matches the active theme instead of a
    fixed-color image asset that would look wrong in dark mode.
    """
    from app.ui.styles import COLOR_CARBON_BLACK, COLOR_PAPER_WHITE
    from app.ui.theme import is_dark_mode

    color = QColor(COLOR_PAPER_WHITE if is_dark_mode() else COLOR_CARBON_BLACK)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)

    painter.translate(size / 2, size / 2)
    painter.rotate(-45)
    shaft = QRectF(-size * 0.11, -size * 0.42, size * 0.22, size * 0.62)
    painter.drawRoundedRect(shaft, size * 0.05, size * 0.05)
    tip = QPolygonF([
        QPointF(shaft.left(), shaft.bottom()),
        QPointF(shaft.right(), shaft.bottom()),
        QPointF(0, shaft.bottom() + size * 0.22),
    ])
    painter.drawPolygon(tip)
    painter.end()
    return QIcon(pixmap)


def make_edit_icon_button(on_click, tooltip: str = "Edit details") -> QPushButton:
    """A small pencil-icon button for one table row, used in every list
    screen's trailing "Actions" column.

    Every module's table used to open its edit/detail dialog on
    doubleClicked - a hidden gesture with no visible affordance, so
    there was no way to discover "double-click a row to edit it" without
    already being told. This button makes that action visible instead:
    each row gets its own clickable icon, and double-click is dropped
    entirely (see each *_window.py for the removed doubleClicked
    connection) so there is exactly one, discoverable way to open a row.
    """
    button = QPushButton()
    button.setIcon(_draw_pencil_icon())
    button.setIconSize(QSize(15, 15))
    button.setFixedSize(28, 28)
    button.setToolTip(tooltip)
    button.setObjectName("rowIconButton")
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(on_click)
    return button


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
