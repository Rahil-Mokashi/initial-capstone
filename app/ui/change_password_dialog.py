"""Self-service password change, used both voluntarily (a "Change
Password" button any logged-in user can reach) and as a forced,
un-skippable step right after login when the account's password was
just set by an admin (User.must_change_password) - see UserService.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.core.exceptions import AppError
from app.ui.qt_utils import describe_unexpected_error


class ChangePasswordDialog(QDialog):
    def __init__(self, user_service, actor_user_id: str, forced: bool = False, parent=None):
        super().__init__(parent)
        self._user_service = user_service
        self._actor_user_id = actor_user_id
        self._forced = forced

        self.setWindowTitle("Set a new password" if forced else "Change Password")
        self.setMinimumWidth(380)
        if forced:
            # No way out except successfully setting a new password -
            # an admin-assigned password must not stay in place silently.
            self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        layout = QVBoxLayout()

        if forced:
            notice = QLabel("Your password was set by an administrator. Choose a new one to continue.")
            notice.setWordWrap(True)
            notice.setObjectName("subtitle")
            layout.addWidget(notice)

        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input.setPlaceholderText("At least 8 chars, upper/lower/digit")
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)

        form = QFormLayout()
        form.addRow("Current password", self.current_password_input)
        form.addRow("New password", self.new_password_input)
        form.addRow("Confirm new password", self.confirm_password_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        save_button = QPushButton("Set password")
        save_button.clicked.connect(self._save)

        button_row = QHBoxLayout()
        button_row.addStretch()
        if not forced:
            cancel_button = QPushButton("Cancel")
            cancel_button.setObjectName("secondaryButton")
            cancel_button.clicked.connect(self.reject)
            button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        self.setLayout(layout)

    def reject(self) -> None:
        if self._forced:
            return
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._forced:
            event.ignore()
            return
        super().closeEvent(event)

    def _save(self) -> None:
        self.error_label.hide()
        if self.new_password_input.text() != self.confirm_password_input.text():
            self._show_error("New password and confirmation do not match.")
            return
        try:
            self._user_service.change_own_password(
                self._actor_user_id,
                self.current_password_input.text(),
                self.new_password_input.text(),
            )
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
