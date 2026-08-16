"""User-reported (2026-08-16): the dashboard felt unbalanced (top bar
margins didn't match the body's) and unresponsive (the card grid was
pinned at a hardcoded 4 columns regardless of window width). Fixes:
DASHBOARD_PAGE_MARGIN shared by the top bar and body, and
compute_dashboard_columns replacing the hardcoded column count.
"""

import pytest

from app.ui.main_window import (
    DASHBOARD_CARD_TARGET_WIDTH,
    DASHBOARD_MAX_CARD_COLUMNS,
    DASHBOARD_PAGE_MARGIN,
    compute_dashboard_columns,
)


def test_columns_never_exceed_the_configured_maximum():
    assert compute_dashboard_columns(4000) == DASHBOARD_MAX_CARD_COLUMNS


def test_columns_never_go_below_one_even_on_a_tiny_window():
    assert compute_dashboard_columns(0) == 1
    assert compute_dashboard_columns(100) == 1


def test_columns_scale_down_as_the_window_narrows():
    wide = compute_dashboard_columns(1600)
    narrow = compute_dashboard_columns(700)
    assert narrow < wide


def test_columns_match_the_minimum_supported_window_width():
    # MainWindow.setMinimumSize(960, 620) - at that width there should
    # be room for more than one column, not a squeeze down to one.
    assert compute_dashboard_columns(960) >= 2


@pytest.mark.parametrize("width", [960, 1024, 1280, 1440, 1920])
def test_columns_are_always_within_bounds(width):
    columns = compute_dashboard_columns(width)
    assert 1 <= columns <= DASHBOARD_MAX_CARD_COLUMNS


def test_a_column_boundary_produces_exactly_the_expected_count():
    # Exactly enough width for 3 columns and no more.
    width = 2 * DASHBOARD_PAGE_MARGIN + 3 * DASHBOARD_CARD_TARGET_WIDTH
    assert compute_dashboard_columns(width) == 3
    assert compute_dashboard_columns(width - 1) == 2
