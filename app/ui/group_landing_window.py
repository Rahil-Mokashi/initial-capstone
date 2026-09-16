"""Landing page for one sidebar group (Masters/Operations/Settings,
2026-09-16 navigation restructure) - a titled tile per module the acting
role can reach, grouped under subheadings rather than one flat grid.
Reports has no landing page of its own: ReportsHubWindow already fills
this exact role (see main_window.py's _open_reports).

Reads MainWindow._card_groups directly (see main_window.py) - there is
no second, parallel list of tiles here. `subgroups` is the exact
per-group slice of that structure: `[(subheading, [(title, subtitle,
factory, permission), ...])]`.

Matches the client-supplied Morex reference (docs/reference/) for the
title/description/card-grid shape, but deliberately does NOT copy its
one flat grid of a dozen-plus undifferentiated tiles per group -
subheadings keep a page with many modules (Operations) scannable
instead of a wall of identical-looking cards.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt_utils import apply_hard_shadow
from app.ui.widgets import GridBackgroundWidget

LANDING_GRID_COLUMNS = 3


class ModuleTileCard(QWidget):
    """One clickable tile: a title and a real, specific one-line
    description of what the screen does - never filler ("Manage X
    records"). A plain QWidget (not QPushButton) because it needs a
    two-line rich layout; clickability is a custom no-arg Signal plus a
    mousePressEvent override, the same shape this app already uses for
    non-button clickable surfaces."""

    clicked = Signal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("moduleTileCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("subtitle")
        subtitle_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        self.setLayout(layout)

        apply_hard_shadow(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class GroupLandingWindow(QWidget):
    """One sidebar group's landing page: title, one-line description,
    then every visible module in the group as a ModuleTileCard, grouped
    under subheadings. A subheading with no visible item (every module
    under it gated out for this role) is skipped entirely rather than
    shown empty - the same "an empty group renders nothing" rule
    MainWindow._is_card_visible already enforces one level up.
    """

    def __init__(self, group_title: str, description: str, subgroups, is_card_visible, open_subpage=None):
        super().__init__()
        # Set by MainWindow when opened as an embedded page, so a tile
        # click pushes a page onto the shared content stack (with a
        # breadcrumb back to this landing page) instead of opening a
        # second top-level window - the same open_subpage convention
        # ReportsHubWindow already uses. Left None for direct,
        # standalone construction (e.g. a test that never clicks a tile).
        self._open_subpage = open_subpage

        self.setWindowTitle(group_title)

        title = QLabel(group_title)
        title.setObjectName("title")

        subtitle = QLabel(description)
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(24)

        any_visible = False
        for subheading, items in subgroups:
            visible_items = [item for item in items if is_card_visible(item[3])]
            if not visible_items:
                continue
            any_visible = True

            heading_label = QLabel(subheading.upper())
            heading_label.setObjectName("dashGroupLabel")

            grid = QGridLayout()
            grid.setSpacing(16)
            for column in range(LANDING_GRID_COLUMNS):
                grid.setColumnStretch(column, 1)
            for index, (item_title, item_subtitle, factory, _permission) in enumerate(visible_items):
                row, column = divmod(index, LANDING_GRID_COLUMNS)
                card = ModuleTileCard(item_title, item_subtitle)
                card.clicked.connect(lambda _checked=False, t=item_title, f=factory: self._open(t, f))
                grid.addWidget(card, row, column)

            section = QVBoxLayout()
            section.setSpacing(12)
            section.addWidget(heading_label)
            section.addLayout(grid)
            content_layout.addLayout(section)

        if not any_visible:
            empty = QLabel("Nothing available for your role yet.")
            empty.setObjectName("subtitle")
            content_layout.addWidget(empty)

        content_layout.addStretch()

        content_container = QWidget()
        content_container.setLayout(content_layout)

        scroll = QScrollArea()
        scroll.setObjectName("background")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content_container)

        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(24, 24, 24, 24)
        page_layout.setSpacing(16)
        page_layout.addWidget(title)
        page_layout.addWidget(subtitle)
        page_layout.addWidget(scroll, stretch=1)

        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(page_layout)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

    def _open(self, title: str, factory) -> None:
        if self._open_subpage is not None:
            self._open_subpage(title, factory)
