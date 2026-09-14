"""QObject exposed to app/ui/qml/LoginScreen.qml as the `bridge` context
property (wired in app/ui/login_window.py).

All authentication logic still lives in AuthService, exactly as it did
before the QML rewrite (2026-09-02) - this class only adapts that same
call into the property/signal shape QML's declarative bindings need
(a `busy` flag the Sign In button binds its enabled/label state to, an
`error` string the error banner binds its visibility/text to), so no
business rule moved and no rule was duplicated in QML/JS.
"""

import platform

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.services.auth_service import AuthService
from app.ui.qt_utils import describe_unexpected_error
from app.ui.theme import is_dark_mode


def get_device_info() -> str:
    return platform.node() or "unknown-device"


class LoginBridge(QObject):
    errorChanged = Signal()
    busyChanged = Signal()
    loginSucceeded = Signal(dict)

    def __init__(self, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self._auth_service = auth_service
        self._error = ""
        self._busy = False

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, constant=True)
    def darkMode(self) -> bool:
        return is_dark_mode()

    def _set_error(self, text: str) -> None:
        text = text or ""
        if text != self._error:
            self._error = text
            self.errorChanged.emit()

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    @Slot(str, str, name="attemptLogin")
    def attempt_login(self, username: str, password: str) -> None:
        username = (username or "").strip()
        password = password or ""
        self._set_error("")

        if not username or not password:
            self._set_error("Enter both username and password.")
            return

        # Password verification (bcrypt) isn't instant; `busy` disables the
        # Sign In button in QML for the same reason the old widget version
        # disabled it directly - so a double-click can't fire two
        # concurrent authenticate() calls.
        self._set_busy(True)
        try:
            success, user_data, error = self._auth_service.authenticate(
                username, password, device_info=get_device_info()
            )
        except Exception as exc:  # noqa: BLE001 - last resort so a DB/unexpected error can't crash the login screen
            self._set_error(describe_unexpected_error(exc))
            return
        finally:
            self._set_busy(False)

        if not success:
            self._set_error(error or "Login failed.")
            return

        self.loginSucceeded.emit(user_data)
