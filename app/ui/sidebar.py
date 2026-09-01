"""Persistent left-hand navigation sidebar.

This replaces the app's previous "the dashboard is the only place to
navigate from" model (2026-08-16) with the client's requested design -
a permanent nav dock, per the client-supplied reference mockups
(2026-08-24). That earlier decision was a deliberate declutter; this is
a deliberate, explicit reversal of it, not an oversight.

Every module screen (Sales, Tanks, Procurement, ...) is now an embedded
page inside MainWindow's own content area rather than a separate
top-level window (2026-08-25) - the sidebar reflects which one is
currently open via `set_active`, the same way a browser highlights the
current tab.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

SIDEBAR_WIDTH = 260

# Shared with MainWindow's top bar (see main_window.py) so the brand
# block and the top bar - two visually separate widgets sitting side by
# side along the same top edge - line up on an identical bottom border
# instead of each sizing itself independently off its own font metrics.
HEADER_HEIGHT = 88


class SidebarNavItem(QPushButton):
    """One clickable row in the sidebar: a plain text label."""

    def __init__(self, label: str, on_click, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarNavItem")
        self.setText(label)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("active", False)
        self.clicked.connect(on_click)

    def set_active(self, active: bool) -> None:
        """Qt does not restyle a widget when a property used in a
        stylesheet selector changes on its own - the same unpolish/polish
        dance MainWindow already uses for the Alerts button's tone."""
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """Fixed-width, full-height navigation dock.

    `groups` is the exact (group_label, [(title, subtitle, handler,
    permission), ...]) structure MainWindow already builds its
    dashboard quick-access cards from, passed straight through rather
    than duplicated - the sidebar and the dashboard's own card grid read
    from one source of truth, so a new module can never show up in one
    without the other.

    `is_card_visible` is MainWindow's existing permission check
    (accepts a single Permission or a tuple), reused as-is.
    """

    def __init__(self, app_name: str, device_label: str, groups, is_card_visible, footer_actions, home_action, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._nav_items: dict[str, SidebarNavItem] = {}

        brand_title = QLabel(app_name)
        brand_title.setObjectName("sidebarBrandTitle")
        brand_title.setWordWrap(True)

        brand_subtitle = QLabel(device_label)
        brand_subtitle.setObjectName("sidebarBrandSubtitle")

        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(20, 24, 20, 20)
        brand_layout.setSpacing(2)
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_subtitle)
        brand_block = QWidget()
        brand_block.setObjectName("sidebarBrandBlock")
        brand_block.setAttribute(Qt.WA_StyledBackground, True)
        brand_block.setFixedHeight(HEADER_HEIGHT)
        brand_block.setLayout(brand_layout)

        nav_layout = QVBoxLayout()
        nav_layout.setContentsMargins(12, 16, 12, 16)
        nav_layout.setSpacing(4)

        home_title, home_handler = home_action
        home_item = SidebarNavItem(home_title, home_handler)
        self._nav_items[home_title] = home_item
        nav_layout.addWidget(home_item)
        nav_layout.addSpacing(12)

        for group_label, items in groups:
            visible_items = [
                (title, handler)
                for title, subtitle, handler, permission in items
                if is_card_visible(permission)
            ]
            if not visible_items:
                continue
            group_label_widget = QLabel(group_label)
            group_label_widget.setObjectName("sidebarGroupLabel")
            nav_layout.addWidget(group_label_widget)
            for title, handler in visible_items:
                item = SidebarNavItem(title, handler)
                self._nav_items[title] = item
                nav_layout.addWidget(item)
            nav_layout.addSpacing(12)
        nav_layout.addStretch()

        nav_content = QWidget()
        nav_content.setLayout(nav_layout)

        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("sidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QScrollArea.NoFrame)
        nav_scroll.setWidget(nav_content)

        footer_layout = QVBoxLayout()
        footer_layout.setContentsMargins(12, 12, 12, 16)
        footer_layout.setSpacing(4)
        for title, handler in footer_actions:
            footer_layout.addWidget(SidebarNavItem(title, handler))
        footer_block = QWidget()
        footer_block.setObjectName("sidebarFooterBlock")
        footer_block.setAttribute(Qt.WA_StyledBackground, True)
        footer_block.setLayout(footer_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(brand_block)
        layout.addWidget(nav_scroll, stretch=1)
        layout.addWidget(footer_block)
        self.setLayout(layout)

    def set_active(self, key: str | None) -> None:
        """Highlight the nav row for the currently open page (`key` is
        that page's title, matching what MainWindow passed as the label
        for this same handler). `None` clears every highlight, used when
        a screen with no matching nav row (e.g. Alerts) is open."""
        for title, item in self._nav_items.items():
            item.set_active(title == key)
