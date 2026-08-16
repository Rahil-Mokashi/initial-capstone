"""Shared print-preview helper (CLAUDE.md Reporting Rules: every
important report must support PRINT and PRINT PREVIEW as distinct
capabilities, not just a direct-to-printer dialog). QPrintPreviewDialog
shows a paginated preview with zoom/page-navigation controls and its
own toolbar Print button, so routing every "Print" action through it
gives both capabilities from one dialog rather than two separate flows.
"""

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget


def show_print_preview(html: str, parent: QWidget) -> None:
    document = QTextDocument()
    document.setHtml(html)

    printer = QPrinter(QPrinter.HighResolution)
    preview = QPrintPreviewDialog(printer, parent)
    preview.paintRequested.connect(document.print_)
    preview.exec()
