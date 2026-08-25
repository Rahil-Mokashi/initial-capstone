"""Light/dark mode (2026-08-24, user-requested): the persisted
preference (app/ui/theme.py) and the two stylesheet variants it selects
between (app/ui/styles.py's build_stylesheet).
"""

import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def isolated_settings(monkeypatch):
    """Points app.ui.theme's QSettings at a throwaway INI file instead of
    the real per-machine store (the Windows registry), so a test run can
    never read or clobber whatever the user actually has saved."""
    import app.ui.theme as theme_module
    from PySide6.QtCore import QSettings

    store: dict[str, object] = {}

    class FakeSettings:
        def value(self, key, default=None, type=None):  # noqa: A002 - matches QSettings' own signature
            value = store.get(key, default)
            return type(value) if type is not None else value

        def setValue(self, key, value):  # noqa: N802 - matches QSettings' own method name
            store[key] = value

    monkeypatch.setattr(theme_module, "QSettings", lambda *a, **k: FakeSettings())
    return store


def test_dark_mode_defaults_to_light(isolated_settings):
    from app.ui.theme import is_dark_mode

    assert is_dark_mode() is False


def test_set_dark_mode_round_trips(isolated_settings):
    from app.ui.theme import is_dark_mode, set_dark_mode

    set_dark_mode(True)
    assert is_dark_mode() is True

    set_dark_mode(False)
    assert is_dark_mode() is False


def test_light_and_dark_stylesheets_differ(qapp):
    from app.ui.styles import build_stylesheet

    light = build_stylesheet(dark=False)
    dark = build_stylesheet(dark=True)

    assert light != dark
    # The page canvas is the clearest single difference: light mode's is a
    # near-white, dark mode's is Carbon Black - checked against the exact
    # selector block rather than just searching for "#000000" anywhere,
    # since one surface (the login hero panel) is deliberately fixed black
    # in BOTH modes.
    assert "QMainWindow, QWidget#background {\n    background-color: #f9f9f9;" in light
    assert "QMainWindow, QWidget#background {\n    background-color: #000000;" in dark


def test_default_stylesheet_export_is_light_mode(qapp):
    from app.ui.styles import STYLESHEET, build_stylesheet

    assert STYLESHEET == build_stylesheet(dark=False)


def test_apply_hard_shadow_picks_theme_color(qapp, isolated_settings, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QWidget

    from app.ui.qt_utils import apply_hard_shadow
    from app.ui.styles import DARK_SHADOW_COLOR, LIGHT_SHADOW_COLOR
    from app.ui.theme import set_dark_mode

    # The soft card shadow (2026-08-25 reskin) applies its base color at
    # low opacity rather than full alpha, so the expected colors below
    # carry the same alpha apply_hard_shadow() itself sets.
    expected_light = QColor(LIGHT_SHADOW_COLOR)
    expected_light.setAlpha(46)
    expected_dark = QColor(DARK_SHADOW_COLOR)
    expected_dark.setAlpha(46)

    set_dark_mode(False)
    light_widget = QWidget()
    apply_hard_shadow(light_widget)
    assert light_widget.graphicsEffect().color() == expected_light

    set_dark_mode(True)
    dark_widget = QWidget()
    apply_hard_shadow(dark_widget)
    assert dark_widget.graphicsEffect().color() == expected_dark


def test_apply_hard_shadow_explicit_color_overrides_theme(qapp, isolated_settings):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QWidget

    from app.ui.qt_utils import apply_hard_shadow

    expected = QColor("#123456")
    expected.setAlpha(46)

    widget = QWidget()
    apply_hard_shadow(widget, color="#123456")
    assert widget.graphicsEffect().color() == expected
