"""Light/dark mode: a personal display preference, not shared business
data - so it is stored via QSettings (Qt's native per-machine settings
store, the registry on Windows) rather than through the app's own
SQLite database and service/audit-log layers the way company profile
settings are. It has no bearing on any other user's session and does
not need RBAC or an audit trail.

Defaults to light mode whenever nothing has been saved yet, so a fresh
install or a settings store wiped by re-imaging a machine never starts
in dark mode by surprise.
"""

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

_SETTINGS_ORG = "PetrolPumpERP"
_SETTINGS_APP = "Desktop"
_DARK_MODE_KEY = "ui/dark_mode"


def is_dark_mode() -> bool:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return settings.value(_DARK_MODE_KEY, False, type=bool)


def set_dark_mode(enabled: bool) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_DARK_MODE_KEY, enabled)


def apply_theme(app: QApplication) -> None:
    """Applies the currently-saved mode's stylesheet to the whole app,
    and repaints every existing widget.

    The repaint loop matters for content this app draws itself rather
    than through QSS - GridBackgroundWidget's dot texture and
    apply_hard_shadow()'s offset shadow both read is_dark_mode() at
    paint time, but nothing tells an already-painted widget that the
    mode just changed. setStyleSheet() alone re-polishes QSS-driven
    appearance (colors, borders) automatically; it does not repaint a
    custom paintEvent, so that half needs forcing explicitly here.
    """
    from app.ui.styles import build_stylesheet

    app.setStyleSheet(build_stylesheet(is_dark_mode()))
    for widget in app.allWidgets():
        widget.update()
