"""Small reusable widgets shared across screens - kept separate from
qt_utils.py (plain functions) since these are actual QWidget subclasses."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QDialog, QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget

from app.core.constants import DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT, VarianceClassification
from app.ui.qt_utils import apply_hard_shadow


class GridBackgroundWidget(QWidget):
    """A background surface painted with the design system's subtle
    dot-grid texture ("Section with Grid Pattern": a flat white section
    "feels unfinished" without it - a sparse grid reinforces the
    engineering-blueprint feel the rest of the palette goes for).

    Piloted on just the login screen and dashboard (2026-08-24), then
    rolled out to every window's own top-level background once that
    pilot was confirmed to read fine behind dense tables too rather than
    as noise - see PROJECT_CONTEXT.md for that follow-up.

    Painting the dots in an overridden paintEvent (rather than via QSS)
    is the same reason apply_hard_shadow() lives in Python instead of
    styles.py: QSS has no repeating-pattern/background-image support
    that works reliably without bundling image assets, so this is drawn
    directly with QPainter instead.
    """

    DOT_SPACING = 20

    def __init__(self, parent=None, force_dark_dots: bool = False):
        super().__init__(parent)
        # Required for this widget's own QSS background-color/border
        # (set via its objectName selector in styles.py) to actually
        # paint - a bare QWidget subclass silently ignores stylesheet
        # backgrounds without this, a documented Qt/QSS gotcha already
        # noted elsewhere in this codebase (see AlertCard).
        self.setAttribute(Qt.WA_StyledBackground, True)
        # The login hero panel is a fixed black surface regardless of the
        # app's light/dark toggle (see styles.py's login-panel docstring),
        # so it always needs the light-toned dot color - the normal
        # theme-read below would pick the near-black LIGHT_DOT_COLOR
        # whenever the app itself is in light mode, which is invisible
        # against a black panel.
        self._force_dark_dots = force_dark_dots

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        # Read fresh each paint rather than cached at construction, so a
        # live theme toggle (app.ui.theme.apply_theme's repaint loop)
        # actually changes which color gets drawn - black dots would be
        # invisible against dark mode's near-black page, the same reason
        # apply_hard_shadow() cannot use a fixed color either.
        from app.ui.styles import DARK_DOT_COLOR, LIGHT_DOT_COLOR
        from app.ui.theme import is_dark_mode

        dot_color = QColor(*(DARK_DOT_COLOR if (self._force_dark_dots or is_dark_mode()) else LIGHT_DOT_COLOR))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        for x in range(0, self.width(), self.DOT_SPACING):
            for y in range(0, self.height(), self.DOT_SPACING):
                painter.drawRect(x, y, 1, 1)
        painter.end()


class ConfirmDialog(QDialog):
    """A themed replacement for QMessageBox.question().

    Native QMessageBox dialogs keep the OS's own title bar and icon
    chrome regardless of this app's stylesheet - they only pick up
    button colors, not the card border/shadow/radius language used
    everywhere else. That mismatch is worst exactly where it matters
    most: destructive confirmations (void a sale, close a shift, remove
    a document), the moments where an operator's trust in what they are
    about to click matters.

    `buttons` is an ordered list of (label, object_name) pairs, e.g.
    `[("Cancel", "secondaryButton"), ("Close Shift", "dangerButton")]`
    - object_name selects one of this app's existing button QSS styles
    (or "" for the default filled/primary look), so a confirm dialog
    always uses colors already established elsewhere rather than
    introducing new ones.
    """

    def __init__(self, parent, title: str, text: str, buttons):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._chosen: str | None = None

        message = QLabel(text)
        message.setObjectName("subtitle")
        message.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch()
        for label, object_name in buttons:
            button = QPushButton(label)
            if object_name:
                button.setObjectName(object_name)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, chosen=label: self._choose(chosen))
            button_row.addWidget(button)

        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(20)
        layout.addWidget(message)
        layout.addLayout(button_row)
        self.setLayout(layout)
        self.setMinimumWidth(380)

    def _choose(self, label: str) -> None:
        self._chosen = label
        self.accept()


def confirm_dialog(parent, title: str, text: str, buttons) -> str | None:
    """Shows a ConfirmDialog and returns the label of the button the
    user clicked, or None if they dismissed it without choosing (Esc,
    the window's close button)."""
    dialog = ConfirmDialog(parent, title, text, buttons)
    dialog.exec()
    return dialog._chosen


def stock_percent(current_stock, capacity) -> float:
    """Shared by TankGaugeCard and its tests: current stock as a percent
    of capacity, clamped to [0, 100] (a book-stock overshoot past
    capacity, or a not-yet-possible negative reading, should still
    render as a sane gauge rather than an out-of-range fill)."""
    capacity_f = float(capacity)
    if capacity_f <= 0:
        return 0.0
    return max(0.0, min(100.0, float(current_stock) / capacity_f * 100))


class _GaugeFill(QWidget):
    """The painted fill portion of a TankGaugeCard's level bar.

    Kept as its own tiny widget, separate from the QSS-styled track
    (border/radius/empty background all live in styles.py as ordinary
    declarative QSS) so only the fill itself needs QPainter - the same
    split GridBackgroundWidget uses between its QSS background and its
    hand-painted dots.
    """

    def __init__(self, percent: float, low: bool, parent=None):
        super().__init__(parent)
        self._percent = percent
        # Plain black/white for a routine reading (matching the reference
        # mockup's own tank gauge, which fills with plain black), red for
        # "running low" - the same danger tone StatCard's "warning" tone
        # and the whole app's alert vocabulary use, so a user who already
        # knows what red means there reads this gauge the same way. Read
        # fresh at construction time (not cached) since a live theme
        # toggle rebuilds this widget along with everything else.
        from app.ui.styles import COLOR_ALERT_RED, COLOR_CARBON_BLACK, COLOR_PAPER_WHITE
        from app.ui.theme import is_dark_mode

        routine_color = COLOR_PAPER_WHITE if is_dark_mode() else COLOR_CARBON_BLACK
        self._color = QColor(COLOR_ALERT_RED if low else routine_color)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        fill_height = round(self.height() * self._percent / 100)
        painter.drawRect(0, self.height() - fill_height, self.width(), fill_height)
        painter.end()


class TankGaugeCard(QWidget):
    """A single tank's stock level as a vertical fill gauge - the
    clearest single visual element in the client's reference mockups,
    and (so far) the only one of their custom data visualizations
    actually built; the physical-vs-book variance bars and the
    per-attendant sales chart remain deferred, see PROJECT_CONTEXT.md.

    Takes plain values rather than a Tank ORM object so it has no
    dependency on the service/model layer and can be unit-tested with
    bare numbers.
    """

    def __init__(self, code: str, fuel_type: str, status: str, current_stock, capacity, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        percent = stock_percent(current_stock, capacity)
        is_low = percent <= DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT

        title = QLabel(code)
        title.setObjectName("sectionTitle")

        status_label = QLabel(status.upper())
        status_label.setObjectName("statusTagActive" if status == "active" else "statusTagInactive")

        fuel_label = QLabel(fuel_type)
        fuel_label.setObjectName("subtitle")

        track = QWidget()
        track.setObjectName("gaugeTrack")
        track.setAttribute(Qt.WA_StyledBackground, True)
        track.setFixedSize(36, 120)
        track_layout = QVBoxLayout(track)
        track_layout.setContentsMargins(2, 2, 2, 2)
        track_layout.addWidget(_GaugeFill(percent, is_low))

        percent_label = QLabel(f"{percent:.0f}%")
        percent_label.setObjectName("statValue")

        stock_label = QLabel(f"{float(current_stock):g} / {float(capacity):g} L")
        stock_label.setObjectName("subtitle")

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(status_label)

        text_column = QVBoxLayout()
        text_column.setSpacing(4)
        text_column.addLayout(header_row)
        text_column.addWidget(fuel_label)
        text_column.addStretch()
        text_column.addWidget(percent_label)
        text_column.addWidget(stock_label)

        layout = QHBoxLayout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)
        layout.addWidget(track)
        layout.addLayout(text_column, stretch=1)
        self.setLayout(layout)
        self.setMinimumHeight(150)

        apply_hard_shadow(self)


def variance_bar_fractions(expected_closing_stock, physical_stock) -> tuple:
    """Shared by VarianceBarCard and its tests: book (expected) and
    physical stock as fractions of whichever is larger, so the two bars
    always fit the same track without either one clipping. Clamped to
    [0, 1] the same defensive way stock_percent clamps its own value -
    a reconciliation record should never carry a negative stock, but the
    bar should render sanely rather than draw backwards if one ever did."""
    expected_f = max(0.0, float(expected_closing_stock))
    physical_f = max(0.0, float(physical_stock))
    larger = max(expected_f, physical_f)
    if larger <= 0:
        return 0.0, 0.0
    return expected_f / larger, physical_f / larger


# The exact severity split NotificationService already uses for the same
# four classifications (app/services/notification_service.py's
# _CLASSIFICATION_SEVERITY) - reused rather than re-decided here, so this
# card and the Alerts screen can never disagree about which variance
# levels count as routine, notable, or a genuine "needs a human"
# situation for the same underlying reconciliation record.
_VARIANCE_COLOR_TONE = {
    VarianceClassification.NORMAL.value: "normal",
    VarianceClassification.WARNING.value: "warning",
    VarianceClassification.INVESTIGATION_REQUIRED.value: "warning",
    VarianceClassification.APPROVAL_REQUIRED.value: "critical",
}


class _VarianceBar(QWidget):
    """One horizontal bar (Book or Physical) inside a VarianceBarCard.
    Only the fill is hand-painted, same split as _GaugeFill/track."""

    def __init__(self, fraction: float, color: QColor, parent=None):
        super().__init__(parent)
        self._fraction = fraction
        self._color = color
        self.setFixedHeight(22)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        fill_width = round(self.width() * self._fraction)
        painter.drawRect(0, 0, fill_width, self.height())
        painter.end()


class VarianceBarCard(QWidget):
    """The latest fuel reconciliation for one tank, as paired Book vs
    Physical bars - the client mockups' "physical-vs-book variance bars"
    visualization, deferred alongside the tank gauge until this pass.

    Takes plain values (not a FuelReconciliation ORM object) for the same
    reason TankGaugeCard does: no service/model dependency, testable with
    bare numbers.
    """

    def __init__(
        self,
        reconciliation_date,
        expected_closing_stock,
        physical_stock,
        variance,
        variance_percent,
        classification: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        from app.ui.styles import COLOR_CARBON_BLACK, COLOR_CAUTION_AMBER, COLOR_PAPER_WHITE
        from app.ui.theme import is_dark_mode

        book_fraction, physical_fraction = variance_bar_fractions(expected_closing_stock, physical_stock)

        tone = _VARIANCE_COLOR_TONE.get(classification, "normal")
        if tone == "critical":
            bar_color = QColor("#f87171" if is_dark_mode() else "#DC2626")
        elif tone == "warning":
            bar_color = QColor(COLOR_CAUTION_AMBER)
        else:
            bar_color = QColor(COLOR_PAPER_WHITE if is_dark_mode() else COLOR_CARBON_BLACK)

        title = QLabel(f"Latest reconciliation — {reconciliation_date}")
        title.setObjectName("sectionTitle")

        variance_label = QLabel(f"Variance: {float(variance):+g} L ({float(variance_percent):+.2f}%)")
        variance_label.setObjectName("subtitle")

        # The same Pill Tag/Badge component the Alerts screen uses for
        # its own severity tags (alertTag + a "tone" property) - reused
        # rather than a fresh style, so this card and the Alerts screen
        # can never look like they disagree about what "warning" means.
        classification_tag = QLabel(classification.replace("_", " ").title())
        classification_tag.setObjectName("alertTag")
        classification_tag.setProperty("tone", "" if tone == "normal" else tone)

        header_row = QHBoxLayout()
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(classification_tag)

        bars_layout = QVBoxLayout()
        bars_layout.setSpacing(10)
        for label_text, value, fraction in (
            ("Book (expected)", expected_closing_stock, book_fraction),
            ("Physical (dipped)", physical_stock, physical_fraction),
        ):
            row_label = QLabel(f"{label_text}: {float(value):g} L")
            row_label.setObjectName("subtitle")

            track = QWidget()
            track.setObjectName("gaugeTrack")
            track.setAttribute(Qt.WA_StyledBackground, True)
            track.setFixedHeight(22)
            track_layout = QHBoxLayout(track)
            track_layout.setContentsMargins(2, 2, 2, 2)
            track_layout.addWidget(_VarianceBar(fraction, bar_color))

            bars_layout.addWidget(row_label)
            bars_layout.addWidget(track)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(header_row)
        layout.addLayout(bars_layout)
        layout.addWidget(variance_label)
        self.setLayout(layout)

        apply_hard_shadow(self)


def chart_points(values, width: float, height: float, padding: float = 10) -> list[tuple[float, float]]:
    """Pure layout helper for SalesTrendChart - maps a list of numeric
    values onto (x, y) pixel coordinates inside a width x height box, with
    `padding` on every side. Testable without Qt, the same split
    stock_percent/variance_bar_fractions already use for their own widgets.

    Returns [] for fewer than 2 values (a single point has no line to
    draw). The y-axis is inverted (a larger value gets a SMALLER y, since
    Qt's origin is top-left) and a flat series (min == max, e.g. every day
    had zero sales) centers the line vertically instead of dividing by
    zero.
    """
    if len(values) < 2:
        return []

    usable_width = max(width - 2 * padding, 1.0)
    usable_height = max(height - 2 * padding, 1.0)
    step = usable_width / (len(values) - 1)

    lowest = min(values)
    highest = max(values)
    span = highest - lowest

    points = []
    for index, value in enumerate(values):
        x = padding + index * step
        if span == 0:
            y = padding + usable_height / 2
        else:
            fraction = (value - lowest) / span
            y = padding + usable_height * (1 - fraction)
        points.append((x, y))
    return points


class SalesTrendChart(QWidget):
    """Hand-painted daily sales revenue line, matching the reference
    mockup's "Fuel Sales Trend" dashboard chart - the first chart in this
    app, drawn with QPainter (same technique as TankGaugeCard/
    VarianceBarCard's fills) rather than a charting library, since nothing
    else in this offline desktop app needs one either.

    `fetch_series(days) -> list[(date, Decimal)]` is called on
    construction and whenever the 7d/30d toggle changes -
    DashboardService.get_recent_daily_sales already returns exactly this
    shape, oldest first.
    """

    def __init__(self, fetch_series, parent=None):
        super().__init__(parent)
        self._fetch_series = fetch_series
        self._series: list[tuple] = []
        self._hover_index: int | None = None
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

        title = QLabel("Sales Trend")
        title.setObjectName("sectionTitle")

        self._range_group = QButtonGroup(self)
        self._range_group.setExclusive(True)
        self._range_7d = QPushButton("7 Days")
        self._range_30d = QPushButton("30 Days")
        for button in (self._range_7d, self._range_30d):
            button.setObjectName("chip")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self._range_group.addButton(button)
        self._range_7d.setChecked(True)
        self._range_7d.toggled.connect(lambda checked: checked and self._load(7))
        self._range_30d.toggled.connect(lambda checked: checked and self._load(30))

        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._range_7d)
        header.addWidget(self._range_30d)

        self._canvas = QWidget()
        self._canvas.setMinimumHeight(160)
        self._canvas.paintEvent = self._paint_canvas  # type: ignore[method-assign]
        self._canvas.mouseMoveEvent = self._canvas_mouse_move  # type: ignore[method-assign]
        self._canvas.mouseLeaveEvent = lambda _event: self._set_hover(None)  # type: ignore[method-assign]
        self._canvas.setMouseTracking(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._canvas, stretch=1)
        self.setLayout(layout)

        self._load(7)

    def _load(self, days: int) -> None:
        self._series = self._fetch_series(days) or []
        self._hover_index = None
        self._canvas.update()

    def _set_hover(self, index: int | None) -> None:
        if index != self._hover_index:
            self._hover_index = index
            self._canvas.update()

    def _canvas_mouse_move(self, event) -> None:
        if len(self._series) < 2:
            return
        points = chart_points([float(v) for _d, v in self._series], self._canvas.width(), self._canvas.height())
        pos = event.position() if hasattr(event, "position") else event.pos()
        nearest_index = min(range(len(points)), key=lambda i: abs(points[i][0] - pos.x()))
        self._set_hover(nearest_index)

        day, value = self._series[nearest_index]
        QToolTip.showText(
            self._canvas.mapToGlobal(QPoint(int(pos.x()), int(pos.y()))),
            f"{day.strftime('%d %b')}: ₹{value:,.2f}",
            self._canvas,
        )

    def _paint_canvas(self, event) -> None:
        from app.ui.styles import COLOR_CARBON_BLACK, COLOR_PAPER_WHITE
        from app.ui.theme import is_dark_mode

        painter = QPainter(self._canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if len(self._series) < 2:
            painter.setPen(QColor("#9a9a9a"))
            painter.drawText(self._canvas.rect(), Qt.AlignCenter, "Not enough data yet")
            painter.end()
            return

        line_color = COLOR_PAPER_WHITE if is_dark_mode() else COLOR_CARBON_BLACK
        values = [float(v) for _d, v in self._series]
        points = chart_points(values, self._canvas.width(), self._canvas.height())

        pen = QPen(QColor(line_color))
        pen.setWidthF(2.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
            painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))

        last_index = len(points) - 1
        for index, (x, y) in enumerate(points):
            is_last = index == last_index
            is_hovered = index == self._hover_index
            radius = 5 if (is_last or is_hovered) else 3
            painter.setPen(QPen(QColor(line_color), 2))
            painter.setBrush(QColor(line_color) if is_last else QColor(COLOR_PAPER_WHITE if not is_dark_mode() else COLOR_CARBON_BLACK))
            painter.drawEllipse(QPoint(int(x), int(y)), radius, radius)

        painter.end()
