"""Settings screen: the company profile and operational preferences.

Exists primarily because every printed document in this app carried no
business identity - a receipt with no pump name, address or GST number is
not a receipt, it is a slip of paper, and it cannot be handed to a
customer. It also gives two separately-deferred items somewhere to live:
the off-device backup location, and (next) print configuration.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import Permission
from app.core.exceptions import AppError
from app.schemas.app_setting import AppSettingUpdate
from app.ui.qt_utils import apply_hard_shadow, chain_enter_to_next_field, describe_unexpected_error
from app.ui.widgets import GridBackgroundWidget


def _card_section(section_title: str, inner_layout) -> QWidget:
    """A rounded white card with a section heading, standing in for
    QGroupBox - QGroupBox keeps native OS chrome (its own title frame)
    that ignores this app's card/shadow QSS entirely, so every other
    screen's section grouping already uses this exact pattern (objectName
    "card" + a "sectionTitle" label) instead. Settings was the one holdout
    still using native group boxes."""
    heading = QLabel(section_title)
    heading.setObjectName("sectionTitle")

    layout = QVBoxLayout()
    layout.setContentsMargins(20, 16, 20, 20)
    layout.setSpacing(12)
    layout.addWidget(heading)
    layout.addLayout(inner_layout)

    card = QWidget()
    card.setObjectName("card")
    card.setAttribute(Qt.WA_StyledBackground, True)
    card.setLayout(layout)
    apply_hard_shadow(card)
    return card


class SettingsWindow(QWidget):
    def __init__(self, settings_service, actor_user_id: str, auth_service):
        super().__init__()
        self._settings_service = settings_service
        self._actor_user_id = actor_user_id
        self._can_manage = auth_service.check_permission(
            actor_user_id, Permission.SETTINGS_MANAGE.value)

        self.setWindowTitle("Settings")
        self.setMinimumSize(680, 640)

        title = QLabel("Settings")
        title.setObjectName("title")

        subtitle = QLabel(
            "The company profile appears at the top of every receipt, statement "
            "and report this application prints."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()

        # --- Company profile ------------------------------------------
        self.company_name_input = QLineEdit()
        self.company_name_input.setPlaceholderText("e.g. Shree Petroleum Services")
        self.address1_input = QLineEdit()
        self.address2_input = QLineEdit()
        self.city_input = QLineEdit()
        self.state_input = QLineEdit()
        self.postal_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.email_input = QLineEdit()
        self.gst_input = QLineEdit()
        self.gst_input.setPlaceholderText("15 characters, e.g. 27AAPFU0939F1ZV")
        self.licence_input = QLineEdit()

        profile_form = QFormLayout()
        profile_form.addRow("Business name", self.company_name_input)
        profile_form.addRow("Address line 1", self.address1_input)
        profile_form.addRow("Address line 2", self.address2_input)
        profile_form.addRow("City", self.city_input)
        profile_form.addRow("State", self.state_input)
        profile_form.addRow("PIN code", self.postal_input)
        profile_form.addRow("Phone", self.phone_input)
        profile_form.addRow("Email", self.email_input)
        profile_form.addRow("GST number", self.gst_input)
        profile_form.addRow("Licence number", self.licence_input)

        profile_box = _card_section("Company profile", profile_form)

        # --- Printing -------------------------------------------------
        self.footer_input = QTextEdit()
        self.footer_input.setPlaceholderText(
            "Printed at the bottom of every receipt, e.g. 'Thank you. Goods "
            "once sold are not returnable.'")
        self.footer_input.setMaximumHeight(80)

        printing_form = QFormLayout()
        printing_form.addRow("Receipt footer", self.footer_input)
        printing_box = _card_section("Printing", printing_form)

        # --- Backups --------------------------------------------------
        self.offsite_dir_input = QLineEdit()
        self.offsite_dir_input.setPlaceholderText("e.g. E:\\PetrolPumpBackups")
        self.browse_button = QPushButton("Browse...")
        self.browse_button.setObjectName("secondaryButton")
        self.browse_button.clicked.connect(self._browse_offsite_dir)

        offsite_row = QHBoxLayout()
        offsite_row.addWidget(self.offsite_dir_input, stretch=1)
        offsite_row.addWidget(self.browse_button)

        backup_form = QFormLayout()
        backup_form.addRow("Off-device backup folder", offsite_row)
        backup_form.addRow("", QLabel(
            "A USB drive or network folder. Backups taken by the app sit on the "
            "same disk as the database, so a copy somewhere else is the only "
            "protection against a failed drive, theft or ransomware."))
        backup_box = _card_section("Backups", backup_form)

        # --- Actions ---------------------------------------------------
        self.save_button = QPushButton("Save Settings")
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self._save)
        self.save_button.setEnabled(self._can_manage)
        if not self._can_manage:
            self.save_button.setToolTip("Only an owner or administrator can change settings.")

        self.reload_button = QPushButton("Discard Changes")
        self.reload_button.setObjectName("secondaryButton")
        self.reload_button.clicked.connect(self.refresh)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.reload_button)
        actions.addWidget(self.save_button)

        body = QVBoxLayout()
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(20)
        body.addWidget(title)
        body.addWidget(subtitle)
        body.addWidget(self.warning_label)
        body.addWidget(self.error_label)
        body.addWidget(profile_box)
        body.addWidget(printing_box)
        body.addWidget(backup_box)
        body.addLayout(actions)
        body.addStretch()

        inner = GridBackgroundWidget()
        inner.setObjectName("background")
        inner.setLayout(body)

        # Scrollable so the form is usable on a short forecourt monitor,
        # the same reason the dashboard body scrolls.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        _page_layout = QVBoxLayout(self)
        _page_layout.setContentsMargins(0, 0, 0, 0)
        _page_layout.addWidget(scroll)

        chain_enter_to_next_field(
            self.company_name_input, self.address1_input, self.address2_input,
            self.city_input, self.state_input, self.postal_input,
            self.phone_input, self.email_input, self.gst_input, self.licence_input)

        self._read_only_if_needed()
        self.refresh()

    # ------------------------------------------------------------------

    def _editable_fields(self):
        return [
            self.company_name_input, self.address1_input, self.address2_input,
            self.city_input, self.state_input, self.postal_input, self.phone_input,
            self.email_input, self.gst_input, self.licence_input,
            self.footer_input, self.offsite_dir_input,
        ]

    def _read_only_if_needed(self) -> None:
        """View-only roles see the profile but cannot change it - the same
        hide-vs-disable rule used everywhere else: disable what they cannot
        do right now, so they can still see the value."""
        if self._can_manage:
            return
        for field in self._editable_fields():
            field.setReadOnly(True)
        self.browse_button.setEnabled(False)

    def refresh(self) -> None:
        self.error_label.hide()
        try:
            setting = self._settings_service.get_settings(self._actor_user_id)
        except AppError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.company_name_input.setText(setting.company_name or "")
        self.address1_input.setText(setting.address_line1 or "")
        self.address2_input.setText(setting.address_line2 or "")
        self.city_input.setText(setting.city or "")
        self.state_input.setText(setting.state or "")
        self.postal_input.setText(setting.postal_code or "")
        self.phone_input.setText(setting.phone or "")
        self.email_input.setText(setting.email or "")
        self.gst_input.setText(setting.gst_number or "")
        self.licence_input.setText(setting.licence_number or "")
        self.footer_input.setPlainText(setting.receipt_footer or "")
        self.offsite_dir_input.setText(setting.offsite_backup_dir or "")

        if not setting.has_company_profile:
            self.warning_label.setText(
                "No business name is set, so printed receipts and reports carry no "
                "identity and cannot be given to a customer.")
            self.warning_label.show()
        else:
            self.warning_label.hide()

    def _browse_offsite_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose a USB drive or network folder")
        if chosen:
            self.offsite_dir_input.setText(chosen)

    def _save(self) -> None:
        self.error_label.hide()
        try:
            self._settings_service.update_settings(self._actor_user_id, AppSettingUpdate(
                company_name=self.company_name_input.text(),
                address_line1=self.address1_input.text(),
                address_line2=self.address2_input.text(),
                city=self.city_input.text(),
                state=self.state_input.text(),
                postal_code=self.postal_input.text(),
                phone=self.phone_input.text(),
                email=self.email_input.text(),
                gst_number=self.gst_input.text(),
                licence_number=self.licence_input.text(),
                receipt_footer=self.footer_input.toPlainText(),
                offsite_backup_dir=self.offsite_dir_input.text(),
            ))
        except (AppError, ValueError) as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(describe_unexpected_error(exc))
            return

        self.refresh()
        QMessageBox.information(self, "Settings saved", "Your settings have been saved.")

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
