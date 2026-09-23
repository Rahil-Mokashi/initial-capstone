"""Shared scaffold for full-page module windows (Tanks, Nozzles,
Employees, Fuel Prices, ...).

Every one of these windows built its own top-level layout the same way:
build a content layout, wrap it in a GridBackgroundWidget "page" surface
for the dot-grid background, then wrap *that* in a zero-margin outer
layout so it fills the window. That six-line block was copy-pasted
identically into each window's __init__ rather than shared - flagged
early on as a "Pending Module" (see PROJECT_CONTEXT.md) and deliberately
deferred each time it came up, since a broad mechanical rewrite across
every window risked more than it was worth at the end of an already large
session. This is the first, incremental step: extract the one piece that
is genuinely byte-for-byte identical everywhere, and migrate windows onto
it one at a time rather than in one large, hard-to-review commit.

Only the page-shell boilerplate is factored out here. The table setup,
button rows, and refresh() logic differ enough window to window (this app
covers list-only, list-with-detail-dialog, and list-with-tabs shapes)
that forcing them into one shared method now would trade a real
simplification for an abstraction that only sort-of fits every case -
exactly what CLAUDE.md's "don't invent abstractions beyond what the task
requires" warns against. Future increments can extract more once several
windows are migrated and the actual common shape (not just the page
shell) is clear from real duplication, not guessed at in advance.
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.ui.widgets import GridBackgroundWidget


class PageWindow(QWidget):
    """Base class for a full-page module window. Call `_build_page(layout)`
    once, at the end of __init__, with the window's fully-built content
    layout - it handles wrapping that layout in the shared page shell."""

    def _build_page(self, layout: QVBoxLayout) -> None:
        container = GridBackgroundWidget()
        container.setObjectName("background")
        container.setLayout(layout)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(container)
