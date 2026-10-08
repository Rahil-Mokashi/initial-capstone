"""Capture one screenshot per screen for the PDF user manual.

Run against a SEEDED DEMO database, never real data:

    set PETROL_PUMP_DB_PATH=%TEMP%\\manual_demo.db
    python scripts/seed_demo_data.py
    python scripts/capture_manual_screenshots.py

Writes docs/manual/img/*.png (full main-window grabs, light theme) and
docs/manual/img/index.json (slug -> title, used by scripts/build_manual_pdf.py).
The admin's forced password change is cleared in the demo DB only, so the
capture can reach the dashboard.
"""

import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QPushButton

app = QApplication.instance() or QApplication([])

import app.ui.theme as theme

theme.is_dark_mode = lambda: False
platform.node = lambda: "COUNTER-PC"

from app.database.connection import SessionLocal
from app.models.user import User
from app.ui.main_window import AppController

OUT = ROOT / "docs" / "manual" / "img"
OUT.mkdir(parents=True, exist_ok=True)
index: dict[str, str] = {}


def settle(seconds: float = 0.6) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def grab(widget, slug: str, title: str, size=(1440, 860), wait: float = 0.6) -> None:
    widget.resize(*size)
    widget.show()
    settle(wait)
    widget.grab().save(str(OUT / f"{slug}.png"))
    index[slug] = title
    print("saved", slug)


def login(controller, username: str, password: str):
    ok, user_data, error = controller._auth_service.authenticate(username, password, device_info="manual-capture")
    if not ok:
        raise SystemExit(f"login {username} failed: {error}")
    controller._show_main_window(user_data)
    controller.main_window.refresh_alert_badge()
    return controller.main_window


def main() -> None:
    session = SessionLocal()
    try:
        for user in session.query(User).filter(User.username == "admin"):
            user.must_change_password = False
        session.commit()
    finally:
        session.close()

    theme.apply_theme(app)
    controller = AppController()
    controller.start()
    grab(controller.login_window, "login", "Login screen", size=(1220, 730), wait=2.0)

    main_window = login(controller, "admin", "Admin@123")
    grab(main_window, "dashboard", "Dashboard", wait=1.5)

    openers = {
        "masters": main_window._open_masters_landing,
        "operations": main_window._open_operations_landing,
        "settings": main_window._open_settings_landing,
        "reports": main_window._open_reports,
    }
    for slug, opener in openers.items():
        opener()
        grab(main_window, f"landing-{slug}", f"{slug.title()} menu")

    for group_label, subgroups in main_window._card_groups:
        for _subheading, entries in subgroups:
            for title, _desc, factory, _perm in entries:
                slug = "page-" + title.lower().replace(" & ", "-").replace(" ", "-")
                main_window._open_module_page(title, factory)
                grab(main_window, slug, title, wait=1.0)

    main_window._open_reports()
    settle()
    hub = main_window._page_stack[-1][0]
    labels = [b.text() for b in hub.findChildren(QPushButton) if b.objectName() == "secondaryButton"]
    for label in labels:
        main_window._open_reports()
        settle(0.3)
        hub = main_window._page_stack[-1][0]
        button = next(b for b in hub.findChildren(QPushButton) if b.text() == label)
        button.click()
        slug = "report-" + label.lower().split(" (")[0].replace(" & ", "-").replace(" ", "-")
        grab(main_window, slug, label, wait=1.2)

    json.dump(index, open(OUT / "index.json", "w"), indent=1)

    controller.main_window.close()
    controller2 = AppController()
    controller2.start()
    attendant = login(controller2, "attendant1", "Passw0rd!")
    grab(attendant, "attendant-dashboard", "Attendant dashboard (restricted role)", wait=1.5)
    json.dump(index, open(OUT / "index.json", "w"), indent=1)


if __name__ == "__main__":
    main()
