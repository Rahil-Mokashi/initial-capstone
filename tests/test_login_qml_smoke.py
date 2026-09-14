"""Catches QML syntax/binding mistakes in LoginScreen.qml / Theme.qml
that a normal pytest run wouldn't otherwise surface - constructing
LoginWindow only fails loudly if the .qml file can't be found at all;
a typo inside a valid file still "loads" (QQuickWidget.Status.Error) but
would only be noticed by a human looking at a blank window.
"""

import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_login_screen_qml_loads_without_errors(qapp):
    from unittest.mock import MagicMock

    from PySide6.QtQuickWidgets import QQuickWidget

    from app.ui.login_window import LoginWindow

    window = LoginWindow(MagicMock())
    try:
        assert window._quick_widget.status() != QQuickWidget.Status.Error, window._quick_widget.errors()
        assert window._quick_widget.rootObject() is not None
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()
