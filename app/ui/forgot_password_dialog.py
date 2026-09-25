"""Self-service completion of an admin-generated password reset code
(UserService.generate_password_reset_code / reset_password_with_code),
reached from the login screen's "Forgot password?" link before the user
is authenticated at all - so unlike every other dialog in app/ui/, this
one takes no actor_user_id and needs no existing session.
"""

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
from app.ui.qt_utils import chain_enter_to_next_field, describe_unexpected_error


class ForgotPasswordDialog(QDialog):
    def __init__(self, user_service, parent=None):
        super().__init__(parent)
        self._user_service = user_service

        self.setWindowTitle("Reset your password")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        notice = QLabel(
            "Ask the person who manages this computer for a reset code, then enter it "
            "below along with a new password. The code only works once and stops working "
            "after a short while."
        )
        notice.setWordWrap(True)
        notice.setObjectName("subtitle")
        layout.addWidget(notice)

        self.username_input = QLineEdit()
        self.code_input = QLineEdit()
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input.setPlaceholderText("At least 8 chars, upper/lower/digit")
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input.returnPressed.connect(self._submit)

        chain_enter_to_next_field(
            self.username_input, self.code_input, self.new_password_input, self.confirm_password_input
        )

        form = QFormLayout()
        form.addRow("Username", self.username_input)
        form.addRow("Reset code", self.code_input)
        form.addRow("New password", self.new_password_input)
        form.addRow("Confirm new password", self.confirm_password_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        submit_button = QPushButton("Reset password")
        submit_button.clicked.connect(self._submit)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel_button)
        button_row.addWidget(submit_button)
        layout.addLayout(button_row)

        self.setLayout(layout)

    def _submit(self) -> None:
        self.error_label.hide()
        if self.new_password_input.text() != self.confirm_password_input.text():
            self._show_error("New password and confirmation do not match.")
            return
        try:
            self._user_service.reset_password_with_code(
                self.username_input.text().strip(),
                self.code_input.text().strip(),
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
