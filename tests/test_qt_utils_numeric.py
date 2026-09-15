"""Tests for the shared money/volume table-cell helper (app/ui/qt_utils.py,
2026-09-15 presentation pass). Covers three separate correctness
concerns: the Indian digit-grouping algorithm itself, the cell's visual
properties (alignment/font), and - the one place a purely cosmetic
change can produce a genuinely wrong answer - that sorting stays
numeric rather than falling back to lexical string sort.
"""

from decimal import Decimal

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from app.ui.qt_utils import (
    NUMERIC_SORT_ROLE,
    format_indian_number,
    money_table_item,
    volume_table_item,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------
# Indian digit grouping
# --------------------------------------------------------------------

def test_no_grouping_needed_under_a_thousand():
    assert format_indian_number(100, 2) == " 100.00"


def test_first_grouping_boundary_at_one_thousand():
    assert format_indian_number(1000, 2) == " 1,000.00"


def test_lakh_groups_in_pairs_after_the_first_three():
    assert format_indian_number(100000, 2) == " 1,00,000.00"


def test_real_report_figure_groups_correctly():
    assert format_indian_number(Decimal("1755916.24"), 2) == " 17,55,916.24"


def test_negative_value_gets_a_leading_minus_not_a_shifted_group():
    assert format_indian_number(Decimal("-6"), 2) == "-6.00"
    assert format_indian_number(Decimal("-175916.24"), 2) == "-1,75,916.24"


def test_zero_gets_the_reserved_sign_space_not_a_minus():
    assert format_indian_number(0, 2) == " 0.00"


def test_volume_uses_three_decimal_places():
    assert format_indian_number(Decimal("1000.5"), 3) == " 1,000.500"


# --------------------------------------------------------------------
# Cell visual properties
# --------------------------------------------------------------------

def test_money_table_item_is_right_aligned(qapp):
    item = money_table_item(Decimal("1000"))
    assert item.textAlignment() == (Qt.AlignRight | Qt.AlignVCenter)


def test_money_table_item_uses_mono_font(qapp):
    from app.ui.styles import FONT_MONO

    item = money_table_item(Decimal("1000"))
    expected_family = FONT_MONO.split(",")[0].strip().strip("'\"")
    assert item.font().families()[0] == expected_family


def test_money_table_item_text_matches_two_decimal_places(qapp):
    item = money_table_item(Decimal("1755916.2"))
    assert item.text() == " 17,55,916.20"


def test_volume_table_item_text_matches_three_decimal_places(qapp):
    item = volume_table_item(Decimal("50.5"))
    assert item.text() == " 50.500"


# --------------------------------------------------------------------
# Numeric (not lexical) sorting - the one place cosmetics can produce a
# wrong answer, per the review that requested this test explicitly.
# --------------------------------------------------------------------

def test_formatted_amounts_carry_the_raw_decimal_for_sorting(qapp):
    item = money_table_item(Decimal("9000"))
    assert item.data(NUMERIC_SORT_ROLE) == Decimal("9000.00")


def test_table_column_sorts_numerically_not_lexically(qapp):
    """The formatted strings are " 900.00", " 9,000.00", " 90,000.00" -
    comparing them as plain text (Python's own `sorted()` on the three
    strings) gives ["9,000.00", "90,000.00", "900.00"]: comma (ASCII 44)
    sorts before a digit (ASCII 48+), so every string starting "9,"
    sorts ahead of "900.00" regardless of magnitude, and the smallest
    value of the three ends up last. Building a real QTableWidget,
    populating it with the shared helper, and sorting it is the only
    way to prove the *whole path* (item -> sort role ->
    QTableWidget.sortItems) works, not just the formatting function in
    isolation."""
    from PySide6.QtWidgets import QTableWidget

    table = QTableWidget(3, 1)
    values = [Decimal("9000"), Decimal("900"), Decimal("90000")]
    for row, value in enumerate(values):
        table.setItem(row, 0, money_table_item(value))

    table.sortItems(0, Qt.AscendingOrder)

    sorted_values = [table.item(row, 0).data(NUMERIC_SORT_ROLE) for row in range(3)]
    assert sorted_values == [Decimal("900.00"), Decimal("9000.00"), Decimal("90000.00")]
