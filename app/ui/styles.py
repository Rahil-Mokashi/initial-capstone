"""Shared visual style for the desktop UI.

A single stylesheet keeps every screen visually consistent. The palette is
deliberately small — one confident primary (indigo) plus one sparingly-used
accent (amber, reserved for the login hero panel) — so the app reads as
eye-catching through hierarchy, whitespace, and one strong color choice
rather than decoration. Kept fast-rendering per problemstatement.md's UX
guidance (speed over visual complexity).
"""

COLOR_BG = "#F5F6FB"
COLOR_SURFACE = "#FFFFFF"
COLOR_BORDER = "#E3E5F0"
COLOR_TEXT = "#1B1E2B"
COLOR_TEXT_MUTED = "#6B7086"

COLOR_PRIMARY = "#4F46E5"
COLOR_PRIMARY_HOVER = "#4338CA"
COLOR_PRIMARY_PRESSED = "#3730A3"
COLOR_PRIMARY_SOFT = "#EEF0FE"

COLOR_ACCENT = "#F59E0B"
COLOR_ACCENT_SOFT = "#FEF3C7"
# Amber dark enough to read as text on COLOR_ACCENT_SOFT.
COLOR_ACCENT_TEXT = "#92610A"

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
    border-radius: 14px;
}}

QLabel#title {{
    font-size: 23px;
    font-weight: 700;
    color: {COLOR_TEXT};
}}

QLabel#subtitle {{
    font-size: 13px;
    color: {COLOR_TEXT_MUTED};
}}

QLabel#errorLabel {{
    color: {COLOR_DANGER};
    background-color: {COLOR_DANGER_BG};
    border-radius: 8px;
    padding: 8px;
    font-size: 12px;
}}

QLabel#warningLabel {{
    color: {COLOR_ACCENT_TEXT};
    background-color: {COLOR_ACCENT_SOFT};
    border-radius: 8px;
    padding: 8px;
}}

QLineEdit {{
    background-color: {COLOR_SURFACE};
    border: 1.5px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 14px;
    selection-background-color: {COLOR_PRIMARY_SOFT};
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

QPushButton:disabled {{
    background-color: #C7C9D9;
    color: #F5F6FB;
}}

QPushButton#secondaryButton {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_TEXT};
    border: 1.5px solid {COLOR_BORDER};
}}

QPushButton#secondaryButton:hover {{
    background-color: {COLOR_BG};
}}

QPushButton#secondaryButton:disabled {{
    background-color: {COLOR_SURFACE};
    color: #B7BACB;
    border: 1.5px solid {COLOR_BORDER};
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
    background-color: {COLOR_PRIMARY_SOFT};
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

QPushButton#dangerButton:disabled {{
    background-color: {COLOR_SURFACE};
    color: #E9B9B9;
    border: 1.5px solid {COLOR_BORDER};
}}

QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {COLOR_SURFACE};
    border: 1.5px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 14px;
}}

QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid {COLOR_PRIMARY};
}}

QDialog {{
    background-color: {COLOR_BG};
}}

QTabWidget::pane {{
    background-color: {COLOR_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {COLOR_TEXT_MUTED};
    padding: 8px 18px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    background-color: {COLOR_SURFACE};
    color: {COLOR_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
}}

QTabBar::tab:hover:!selected {{
    color: {COLOR_TEXT};
}}

QTableWidget {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    gridline-color: {COLOR_BORDER};
    selection-background-color: {COLOR_PRIMARY_SOFT};
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
    border-radius: 10px;
}}

QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
    margin-top: 8px;
}}

/* --- Login hero panel --- */

QWidget#heroPanel {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4F46E5, stop:1 #4338CA);
}}

QLabel#heroTitle {{
    color: white;
    font-size: 30px;
    font-weight: 700;
}}

QLabel#heroTagline {{
    color: #E0E1FB;
    font-size: 14px;
}}

QLabel#heroBullet {{
    color: #EDEEFD;
    font-size: 13px;
}}

QWidget#heroBadge {{
    background-color: rgba(255, 255, 255, 30);
    border-radius: 22px;
}}

QLabel#heroBadgeGlyph {{
    color: white;
    font-size: 22px;
    font-weight: 700;
}}

/* --- Dashboard quick-access cards --- */

QWidget#dashCard {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 14px;
}}

QWidget#dashCard:hover {{
    border: 1px solid {COLOR_PRIMARY};
}}

QLabel#dashCardIcon {{
    background-color: {COLOR_PRIMARY_SOFT};
    color: {COLOR_PRIMARY};
    border-radius: 10px;
    font-size: 18px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}}

QLabel#dashCardTitle {{
    font-size: 15px;
    font-weight: 700;
}}

QLabel#dashCardSubtitle {{
    font-size: 12px;
    color: {COLOR_TEXT_MUTED};
}}

QLabel#dashGreeting {{
    font-size: 24px;
    font-weight: 700;
}}

QLabel#dashDate {{
    font-size: 13px;
    color: {COLOR_TEXT_MUTED};
}}

QLabel#dashGroupLabel {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    color: {COLOR_TEXT_MUTED};
}}

/* --- Dashboard KPI strip --- */

QWidget#statCard {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-left: 4px solid {COLOR_PRIMARY};
    border-radius: 12px;
}}

QWidget#statCard[tone="warning"] {{
    border-left: 4px solid {COLOR_ACCENT};
}}

QLabel#statValue {{
    font-size: 26px;
    font-weight: 800;
}}

QLabel#statValue[tone="warning"] {{
    color: {COLOR_ACCENT};
}}

QLabel#statLabel {{
    font-size: 12px;
    color: {COLOR_TEXT_MUTED};
    font-weight: 600;
}}

/* --- Notifications (problemstatement.md #43) ---
   Severity is carried by a `tone` property rather than three separate
   object names, so the alert widget stays one widget and Qt re-polishes
   it when the severity changes. The colour vocabulary is the one already
   in use elsewhere: danger red for critical, the accent amber that
   warningLabel already uses for warnings, and the primary indigo for
   informational items - no new colours introduced for a new screen. */

QWidget#alertCard {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-left: 4px solid {COLOR_PRIMARY};
    border-radius: 12px;
}}

QWidget#alertCard[tone="critical"] {{
    border-left: 4px solid {COLOR_DANGER};
}}

QWidget#alertCard[tone="warning"] {{
    border-left: 4px solid {COLOR_ACCENT};
}}

QLabel#alertTitle {{
    font-size: 15px;
    font-weight: 700;
}}

QLabel#alertDetail {{
    font-size: 13px;
    color: {COLOR_TEXT_MUTED};
}}

QLabel#alertTag {{
    font-size: 11px;
    font-weight: 700;
    border-radius: 6px;
    padding: 3px 8px;
    background-color: {COLOR_PRIMARY_SOFT};
    color: {COLOR_PRIMARY};
}}

QLabel#alertTag[tone="critical"] {{
    background-color: {COLOR_DANGER_BG};
    color: {COLOR_DANGER};
}}

QLabel#alertTag[tone="warning"] {{
    background-color: {COLOR_ACCENT_SOFT};
    color: {COLOR_ACCENT_TEXT};
}}

/* The top-bar button that opens the alerts screen. It carries its own
   count, so a `tone` of "critical"/"warning" makes an unattended problem
   visible from the dashboard without the operator opening anything. */
QPushButton#alertsButton {{
    background-color: {COLOR_PRIMARY_SOFT};
    color: {COLOR_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 700;
}}

QPushButton#alertsButton:hover {{
    background-color: {COLOR_BORDER};
}}

QPushButton#alertsButton[tone="critical"] {{
    background-color: {COLOR_DANGER_BG};
    color: {COLOR_DANGER};
}}

QPushButton#alertsButton[tone="warning"] {{
    background-color: {COLOR_ACCENT_SOFT};
    color: {COLOR_ACCENT_TEXT};
}}

QLabel#alertEmptyState {{
    font-size: 15px;
    color: {COLOR_SUCCESS};
    background-color: {COLOR_SUCCESS_BG};
    border-radius: 12px;
    padding: 24px;
}}
"""
