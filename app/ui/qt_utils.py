"""Small, shared Qt <-> Python type conversion and error-handling helpers
for the UI layer."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QTableWidgetItem, QWidget

from app.core.logging import logger
from app.core.money import MONEY_QUANTUM, VOLUME_QUANTUM, Numeric


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


# --------------------------------------------------------------------
# Money/volume table cells
# --------------------------------------------------------------------
#
# 2026-09-15, user-requested presentation pass: across every *_window.py
# table, money and volume columns were left-aligned, ungrouped, and
# formatted with inconsistent decimal places down a column (:g strips
# trailing zeros, so 100.5 and 100.50 render differently in the same
# column) - the one thing a person scanning a column of rupee or litre
# figures actually needs (decimal points lined up) was the one thing
# nothing here provided. These two helpers are the single place that
# fixes it, so every table cell gets the same treatment rather than each
# screen inventing its own.
#
# A custom Qt role (not Qt.UserRole - several screens already stash a
# row's own id there on column 0, e.g. ReconciliationsTab.refresh) holds
# the exact Decimal the cell displays, so sorting can compare it
# directly instead of comparing the formatted *text*, where "9,000"
# would otherwise sort after "10,000" - see NumericTableWidgetItem below.
NUMERIC_SORT_ROLE = Qt.UserRole + 1000

# Decimal places are derived from app/core/money.py's own quantums
# (2dp/3dp) rather than repeated as separate literals here, so a change
# to how the app settles money or volume can't quietly desync from how
# it displays them.
_MONEY_DECIMAL_PLACES = -MONEY_QUANTUM.as_tuple().exponent
_VOLUME_DECIMAL_PLACES = -VOLUME_QUANTUM.as_tuple().exponent


def _group_indian(integer_digits: str) -> str:
    """Group a string of digits Indian-style: the last three digits form
    one group, then every remaining pair of digits forms its own group
    working left from there (1,75,916 - not 175,916's Western
    thousands-only grouping). Python's format-spec `,`/`_` separators and
    the stdlib `locale` module both only know Western grouping;
    `locale.format_string` could produce this with an en_IN locale
    installed, but that's a per-machine locale this app cannot assume is
    present on a customer's PC (CLAUDE.md: must work entirely offline,
    with nothing to configure) - so the grouping is implemented directly
    here instead of delegated to either."""
    if len(integer_digits) <= 3:
        return integer_digits
    last_three = integer_digits[-3:]
    remainder = integer_digits[:-3]
    pairs = []
    while len(remainder) > 2:
        pairs.insert(0, remainder[-2:])
        remainder = remainder[:-2]
    if remainder:
        pairs.insert(0, remainder)
    return ",".join(pairs + [last_three])


def format_indian_number(value: Numeric, decimal_places: int) -> str:
    """Render `value` at a fixed number of decimal places, Indian-style
    thousands-grouped, with one leading sign character always present -
    a literal `-` for a negative value, a space otherwise.

    That reserved sign column is the deliberate answer to the alignment
    problem a bare minus sign causes (2026-09-15 user decision): without
    it, a right-aligned column mixing positive and negative figures
    (fuel variance, chiefly - the reference report shows +3, 0, +13,
    -6) has its digits shifted one character wherever a minus sign
    appears, breaking the very decimal-point alignment this whole
    change exists to create. A colour cue was considered and rejected:
    styles.py's own design system reserves colour for status meaning
    only (normal/warning/critical), and a number's sign is not a status
    the app already classifies - reusing colour for it would blur that
    existing rule instead of extending it. Parentheses were the other
    option; a leading sign column was chosen over them because it keeps
    every digit and the decimal point in the exact same column position
    whether or not that particular row is negative, where a trailing
    close-parenthesis shifts the string's own trailing edge instead.
    """
    quantum = Decimal(1).scaleb(-decimal_places)
    quantized = (value if isinstance(value, Decimal) else Decimal(str(value))).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    negative = quantized < 0
    text = f"{abs(quantized):.{decimal_places}f}"
    integer_part, _, fractional_part = text.partition(".")
    grouped = _group_indian(integer_part)
    body = f"{grouped}.{fractional_part}" if decimal_places else grouped
    sign = "-" if negative else " "
    return f"{sign}{body}"


class NumericTableWidgetItem(QTableWidgetItem):
    """A QTableWidgetItem that sorts on the raw Decimal it was built
    from, not on its own formatted display text.

    QTableWidget's default sort compares each item's display text as a
    *string* - fine for names, wrong for numbers: "10,000" sorts before
    "9,000" because "1" < "9" lexically, the exact wrong-answer risk a
    purely cosmetic formatting change can quietly introduce. The raw
    value lives in NUMERIC_SORT_ROLE (set by money_table_item/
    volume_table_item below) and this override compares that instead.
    """

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        self_value = self.data(NUMERIC_SORT_ROLE)
        other_value = other.data(NUMERIC_SORT_ROLE)
        if isinstance(self_value, Decimal) and isinstance(other_value, Decimal):
            return self_value < other_value
        return super().__lt__(other)


def _mono_font() -> QFont:
    """Builds on styles.py's FONT_MONO token rather than a second,
    independent font definition - QSS's `font-family` fallback chain
    has no Python equivalent to reuse directly, so the same family list
    is parsed into a QFont, generic keywords (`monospace`) dropped in
    favour of QFont's own style-hint mechanism for that same fallback
    role. A fixed-width font is not a cosmetic choice here: it is what
    makes the decimal points in a formatted column of numbers actually
    line up vertically, which is the whole point of this change."""
    from app.ui.styles import FONT_MONO

    families = [
        name.strip().strip("'\"")
        for name in FONT_MONO.split(",")
        if name.strip().strip("'\"").lower() != "monospace"
    ]
    font = QFont()
    font.setFamilies(families)
    font.setStyleHint(QFont.Monospace)
    return font


def _numeric_table_item(value: Numeric, decimal_places: int) -> QTableWidgetItem:
    quantum = Decimal(1).scaleb(-decimal_places)
    quantized = (value if isinstance(value, Decimal) else Decimal(str(value))).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    item = NumericTableWidgetItem(format_indian_number(quantized, decimal_places))
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    item.setFont(_mono_font())
    item.setData(NUMERIC_SORT_ROLE, quantized)
    return item


def money_table_item(value: Numeric) -> QTableWidgetItem:
    """A right-aligned, mono, Indian-grouped, 2dp table cell for a money
    figure - matches app/core/money.py's own MONEY_QUANTUM exactly, so
    what's stored/settled and what's displayed can never quietly
    disagree on precision."""
    return _numeric_table_item(value, _MONEY_DECIMAL_PLACES)


def volume_table_item(value: Numeric) -> QTableWidgetItem:
    """The same treatment as money_table_item, at volume's 3dp
    (app/core/money.py's VOLUME_QUANTUM). Also the deliberate choice for
    a nozzle assignment's meter readings (2026-09-15 judgement call):
    a meter reading is a cumulative totalizer count, not itself a fuel
    volume the way a sale or a tank transaction is, but it is stored
    with the identical representation (Decimal, 3dp litres) and a
    reader scanning a column of them benefits from the identical
    alignment - there is no business reason to format the same kind of
    number two different ways just because of where it came from."""
    return _numeric_table_item(value, _VOLUME_DECIMAL_PLACES)
