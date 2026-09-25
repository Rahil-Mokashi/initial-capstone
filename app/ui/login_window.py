"""Login screen. Pure presentation — all authentication logic lives in
AuthService, reached through LoginBridge (app/ui/login_bridge.py).

Rebuilt in QML (2026-09-02, hybrid QML UI upgrade Phase A): the previous
version was a hand-built QWidget form (QLineEdit/QPushButton/QLabel).
This is now a QQuickWidget hosting app/ui/qml/LoginScreen.qml, so the
screen can use Qt Quick's declarative animations (entrance fade, focus/
hover transitions, an animated error banner) that plain QWidget/QSS
cannot express. LoginWindow itself keeps its exact prior contract with
AppController - it is still a QMainWindow and still emits
login_succeeded(dict) - so app/ui/main_window.py needed zero changes.

Every prior redesign note (product name "FuelDesk" distinct from the
rest of the app's "Petrol Pump ERP" branding, the centered-card layout,
the removal of the four flanking callout cards) is preserved in the new
QML file; see app/ui/qml/LoginScreen.qml for the current layout.
"""

import os
import sys

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QMainWindow

from app.core.logging import logger
from app.services.auth_service import AuthService
from app.ui.login_bridge import LoginBridge

PRODUCT_NAME = "FuelDesk"


def _qml_dir() -> str:
    """Where app/ui/qml/ lives at runtime.

    A PyInstaller onefile build unpacks to a fresh temp directory
    (sys._MEIPASS) on every launch, so this can't be resolved relative to
    the current working directory - same reasoning, and same pattern, as
    app/database/migrations.py's _project_root().
    """
    if getattr(sys, "frozen", False):
        root = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "app", "ui", "qml")


class LoginWindow(QMainWindow):
    """Hosts the QML login screen and delegates authentication to
    AuthService via LoginBridge.

    Emits login_succeeded(dict) with the AuthService user_data payload
    (including a session_token) on success - unchanged from the previous
    QWidget version, since AppController listens for exactly this signal
    and nothing else.
    """

    login_succeeded = Signal(dict)

    def __init__(self, auth_service: AuthService):
        super().__init__()
        self._auth_service = auth_service
        self.bridge = LoginBridge(auth_service)
        self.bridge.loginSucceeded.connect(self.login_succeeded.emit)

        self.setWindowTitle(f"{PRODUCT_NAME} — Sign In")
        # Lowered from the previous (640, 780) (2026-09-25, login UI pass):
        # LoginScreen.qml's card now computes its own width from the
        # window's actual size (root.formWidth) instead of using a fixed
        # 380px, so the window can actually be shrunk and the form will
        # reflow instead of clipping - a minimum this tall/wide would have
        # made that responsiveness unreachable, since the window could
        # never get small enough to exercise it.
        self.setMinimumSize(420, 620)

        self._quick_widget = QQuickWidget()
        self._quick_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._quick_widget.rootContext().setContextProperty("bridge", self.bridge)

        qml_path = os.path.join(_qml_dir(), "LoginScreen.qml")
        self._quick_widget.setSource(QUrl.fromLocalFile(qml_path))

        if self._quick_widget.status() == QQuickWidget.Status.Error:
            for error in self._quick_widget.errors():
                logger.error("Failed to load LoginScreen.qml: %s", error.toString())

        # Qt.QueuedConnection is load-bearing here, not a style choice
        # (2026-09-16, user-reported crash - see LoginScreen.qml's own
        # long comment on submitTrigger, and LoginBridge.submit's
        # docstring): LoginScreen.qml never calls into Python from
        # inside its own onAccepted/onClicked handlers - doing so
        # reliably crashed with a genuine native stack overflow, for
        # every field, every Slot, regardless of deferring the call in
        # four different ways. submitTrigger is a plain QML property
        # those handlers touch instead; connecting its own auto-
        # generated submitTriggerChanged signal to bridge.submit with
        # an explicit queued connection is what actually calls into
        # Python - Qt guarantees a queued connection's slot only runs
        # once the event loop is back at its own outermost frame, which
        # is a genuinely different guarantee from QML's own
        # Qt.callLater (tried first; it did not stop the crash, since
        # its callback can still run within the same QML update cycle
        # that delivered the original event).
        root = self._quick_widget.rootObject()
        if root is not None:
            root.submitTriggerChanged.connect(self.bridge.submit, Qt.QueuedConnection)

        self.setCentralWidget(self._quick_widget)

    def find_qml_object(self, object_name: str):
        """Look up a named item inside the loaded QML scene by objectName.

        Exists for tests (see tests/test_login_ui.py) that need to assert
        on QML-side state (e.g. which field has focus) the way the old
        QWidget tests asserted on widget attributes directly - there is no
        equivalent widget attribute to read once the form lives in QML.
        """
        root = self._quick_widget.rootObject()
        return root.findChild(QObject, object_name) if root else None
