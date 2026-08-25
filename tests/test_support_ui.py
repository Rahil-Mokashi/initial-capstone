import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_support_window_shows_offline_and_account_and_backup_guidance(qapp):
    from PySide6.QtWidgets import QLabel

    from app.ui.support_window import SupportWindow

    window = SupportWindow()
    texts = " ".join(label.text() for label in window.findChildren(QLabel))

    assert "works fully offline" in texts
    assert "Users" in texts
    assert "Backups" in texts
