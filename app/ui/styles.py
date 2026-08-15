"""Shared visual style for the desktop UI.

A single stylesheet keeps every screen visually consistent. Kept simple and
fast-rendering per problemstatement.md's UX guidance (speed over visual
complexity) — this is polish via consistent spacing/color/typography, not
heavy decoration.
"""

COLOR_BG = "#F4F6F9"
COLOR_SURFACE = "#FFFFFF"
COLOR_BORDER = "#E2E5EB"
COLOR_TEXT = "#1F2430"
COLOR_TEXT_MUTED = "#6B7280"
COLOR_PRIMARY = "#2563EB"
COLOR_PRIMARY_HOVER = "#1D4ED8"
COLOR_PRIMARY_PRESSED = "#1E40AF"
COLOR_DANGER = "#DC2626"
COLOR_DANGER_BG = "#FEF2F2"
COLOR_DANGER_HOVER = "#B91C1C"
COLOR_SUCCESS_BG = "#ECFDF5"
COLOR_SUCCESS = "#059669"

STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 14px;
    color: {COLOR_TEXT};
}}

QMainWindow, QWidget#background {{
    background-color: {COLOR_BG};
}}

QWidget#card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
}}

QLabel#title {{
    font-size: 22px;
    font-weight: 600;
    color: {COLOR_TEXT};
}}

QLabel#subtitle {{
    font-size: 13px;
    color: {COLOR_TEXT_MUTED};
}}

QLabel#errorLabel {{
    color: {COLOR_DANGER};
    background-color: {COLOR_DANGER_BG};
    border-radius: 6px;
    padding: 8px;
    font-size: 12px;
}}

QLineEdit {{
    background-color: {COLOR_SURFACE};
    border: 1.5px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
}}

QLineEdit:focus {{
    border: 1.5px solid {COLOR_PRIMARY};
}}

QPushButton {{
    background-color: {COLOR_PRIMARY};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
}}

QPushButton:pressed {{
    background-color: {COLOR_PRIMARY_PRESSED};
}}

QPushButton#secondaryButton {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    border: 1.5px solid {COLOR_BORDER};
}}

QPushButton#secondaryButton:hover {{
    background-color: {COLOR_BG};
}}

QWidget#topBar {{
    background-color: {COLOR_SURFACE};
    border-bottom: 1px solid {COLOR_BORDER};
}}

QLabel#userLabel {{
    font-size: 14px;
    font-weight: 600;
}}

QLabel#roleTag {{
    background-color: #EEF2FF;
    color: {COLOR_PRIMARY};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel#statusTagActive {{
    background-color: {COLOR_SUCCESS_BG};
    color: {COLOR_SUCCESS};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel#statusTagInactive {{
    background-color: {COLOR_DANGER_BG};
    color: {COLOR_DANGER};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#dangerButton {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_DANGER};
    border: 1.5px solid #FCA5A5;
}}

QPushButton#dangerButton:hover {{
    background-color: {COLOR_DANGER_BG};
    color: {COLOR_DANGER_HOVER};
}}

QComboBox, QDateEdit {{
    background-color: {COLOR_SURFACE};
    border: 1.5px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 14px;
}}

QComboBox:focus, QDateEdit:focus {{
    border: 1.5px solid {COLOR_PRIMARY};
}}

QDialog {{
    background-color: {COLOR_BG};
}}

QTableWidget {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    gridline-color: {COLOR_BORDER};
    selection-background-color: #DBEAFE;
    selection-color: {COLOR_TEXT};
}}

QHeaderView::section {{
    background-color: {COLOR_BG};
    color: {COLOR_TEXT_MUTED};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
    font-weight: 600;
}}

QListWidget {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}

QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
    margin-top: 8px;
}}
"""
