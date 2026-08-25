"""app/ui/widgets.py - the small reusable widgets shared across screens.
Focused here on TankGaugeCard and its stock_percent() helper
(2026-08-24); GridBackgroundWidget and ConfirmDialog are already
exercised indirectly through the screens that use them.
"""

import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_stock_percent_computes_the_expected_fraction():
    from app.ui.widgets import stock_percent

    assert stock_percent(current_stock=5000, capacity=10000) == 50.0
    assert stock_percent(current_stock=0, capacity=10000) == 0.0
    assert stock_percent(current_stock=10000, capacity=10000) == 100.0


def test_stock_percent_clamps_to_zero_and_hundred():
    from app.ui.widgets import stock_percent

    # A book-stock overshoot past capacity, or a reading that has not
    # yet been corrected below zero, should still render as a sane
    # gauge rather than an out-of-range fill.
    assert stock_percent(current_stock=12000, capacity=10000) == 100.0
    assert stock_percent(current_stock=-500, capacity=10000) == 0.0


def test_stock_percent_handles_zero_capacity_without_dividing_by_zero():
    from app.ui.widgets import stock_percent

    assert stock_percent(current_stock=500, capacity=0) == 0.0


def test_tank_gauge_card_shows_percent_and_stock(qapp):
    from app.ui.widgets import TankGaugeCard

    card = TankGaugeCard("T1", "Petrol", "active", current_stock=2500, capacity=10000)

    from PySide6.QtWidgets import QLabel

    label_texts = [label.text() for label in card.findChildren(QLabel)]
    assert "25%" in label_texts
    assert "2500 / 10000 L" in label_texts
    assert "T1" in label_texts


@pytest.mark.parametrize(
    "current_stock,capacity,expect_low",
    [
        (1900, 10000, True),   # 19% - at/below the shared DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT (20%)
        (2000, 10000, True),   # exactly the threshold - inclusive, matches DashboardService's own <=
        (2100, 10000, False),  # just above the threshold
    ],
)
def test_tank_gauge_card_low_stock_threshold_matches_dashboard(qapp, current_stock, capacity, expect_low):
    """TankGaugeCard's fill must agree with DASHBOARD_LOW_STOCK_THRESHOLD_PERCENT
    exactly - not a separately-chosen number that could quietly drift
    from what the dashboard KPI tile and the notification service
    already call "running low" for the same tanks."""
    from app.ui.styles import COLOR_ALERT_RED, COLOR_CARBON_BLACK, COLOR_PAPER_WHITE
    from app.ui.theme import is_dark_mode
    from app.ui.widgets import TankGaugeCard

    card = TankGaugeCard("T1", "Petrol", "active", current_stock=current_stock, capacity=capacity)
    # Walk down to the _GaugeFill instance via the track's single child widget.
    track = card.layout().itemAt(0).widget()
    gauge_fill = track.layout().itemAt(0).widget()

    routine_color = COLOR_PAPER_WHITE if is_dark_mode() else COLOR_CARBON_BLACK
    expected_color = COLOR_ALERT_RED if expect_low else routine_color
    assert gauge_fill._color.name() == expected_color


def test_variance_bar_fractions_scales_to_the_larger_value():
    from app.ui.widgets import variance_bar_fractions

    # Physical short of book (a shortage) - book is the larger value, so
    # it fills its own track completely and physical is scaled relative to it.
    book, physical = variance_bar_fractions(expected_closing_stock=10000, physical_stock=9800)
    assert book == 1.0
    assert physical == pytest.approx(0.98)

    # Physical over book (a surplus) - the roles invert.
    book, physical = variance_bar_fractions(expected_closing_stock=9800, physical_stock=10000)
    assert physical == 1.0
    assert book == pytest.approx(0.98)

    # Exact match - both bars fill completely, no variance to see.
    assert variance_bar_fractions(expected_closing_stock=5000, physical_stock=5000) == (1.0, 1.0)


def test_variance_bar_fractions_handles_zero_without_dividing_by_zero():
    from app.ui.widgets import variance_bar_fractions

    assert variance_bar_fractions(expected_closing_stock=0, physical_stock=0) == (0.0, 0.0)


def test_variance_bar_card_shows_the_reconciliation_figures(qapp):
    from app.ui.widgets import VarianceBarCard

    card = VarianceBarCard(
        "2026-08-24", expected_closing_stock=10000, physical_stock=9800,
        variance=-200, variance_percent=-2.0, classification="normal",
    )

    from PySide6.QtWidgets import QLabel

    label_texts = [label.text() for label in card.findChildren(QLabel)]
    assert any("Latest reconciliation" in text and "2026-08-24" in text for text in label_texts)
    assert "Book (expected): 10000 L" in label_texts
    assert "Physical (dipped): 9800 L" in label_texts
    assert "Variance: -200 L (-2.00%)" in label_texts
    assert "Normal" in label_texts


def test_chart_points_returns_empty_for_fewer_than_two_values():
    from app.ui.widgets import chart_points

    assert chart_points([], 200, 100) == []
    assert chart_points([5], 200, 100) == []


def test_chart_points_spaces_x_evenly_across_the_width():
    from app.ui.widgets import chart_points

    points = chart_points([1, 2, 3, 4], width=100, height=50, padding=0)
    xs = [x for x, _y in points]
    assert xs == pytest.approx([0, 100 / 3, 200 / 3, 100])


def test_chart_points_maps_the_largest_value_to_the_smallest_y():
    from app.ui.widgets import chart_points

    points = chart_points([10, 50], width=100, height=100, padding=0)
    (_x1, y_low), (_x2, y_high) = points
    # Qt's origin is top-left, so the larger value (50) must get the
    # SMALLER y - a chart that got this backwards would draw upside down.
    assert y_high < y_low


def test_chart_points_flat_series_centers_the_line_without_dividing_by_zero():
    from app.ui.widgets import chart_points

    points = chart_points([7, 7, 7], width=90, height=60, padding=0)
    ys = [y for _x, y in points]
    assert ys == pytest.approx([30, 30, 30])


def test_sales_trend_chart_loads_the_initial_7_day_range(qapp):
    from app.ui.widgets import SalesTrendChart
    from datetime import date, timedelta
    from decimal import Decimal

    calls = []

    def fetch(days):
        calls.append(days)
        return [(date.today() - timedelta(days=offset), Decimal(offset)) for offset in range(days - 1, -1, -1)]

    chart = SalesTrendChart(fetch)
    assert calls == [7]
    assert len(chart._series) == 7

    chart._range_30d.setChecked(True)
    assert calls == [7, 30]
    assert len(chart._series) == 30


@pytest.mark.parametrize(
    "classification,expected_tone",
    [
        ("normal", ""),
        ("warning", "warning"),
        ("investigation_required", "warning"),
        ("approval_required", "critical"),
    ],
)
def test_variance_bar_card_tone_matches_notification_service_severity(qapp, classification, expected_tone):
    """Must never disagree with NotificationService's own
    _CLASSIFICATION_SEVERITY mapping for the same four classifications -
    same reconciliation, same severity, wherever it's shown."""
    from app.ui.widgets import VarianceBarCard

    card = VarianceBarCard(
        "2026-08-24", expected_closing_stock=10000, physical_stock=10000,
        variance=0, variance_percent=0.0, classification=classification,
    )
    from PySide6.QtWidgets import QLabel

    tag = next(label for label in card.findChildren(QLabel) if label.objectName() == "alertTag")
    assert tag.property("tone") == expected_tone
