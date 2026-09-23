"""Regenerate docs/screenshots/*.png by rendering the real Qt widgets directly.

Uses QWidget.grab(), which renders the widget's own backing store into a
QPixmap - it does not depend on OS window focus, stacking order, or a
screen capture of any kind. The offscreen QPA platform is deliberately NOT
used here since it lacks real system font rendering on this machine.

Runs against an ISOLATED temporary SQLite database (never the real
dev/production petrol_pump.db), the same pattern
scripts/verify_navigation_and_alerts.py already established, so this can
be run freely without touching real data or depending on a manager1
account that may or may not exist in whatever database happens to be
configured. Earlier versions of this script connected to whatever
PETROL_PUMP_DB_PATH/default pointed at and assumed a "manager1" login
already existed there - safe only by accident, and it would silently fail
(or silently succeed against real data) depending on what that happened
to be. Fixed 2026-09-23 while finally regenerating these two screenshots
(ROADMAP.md Next Immediate Task #2, paused since 2026-08-16).

Run with: python scripts/capture_screenshots.py
"""

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

import app.database.connection as db_connection
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TMP_DIR = Path(tempfile.mkdtemp(prefix="petrolpump_screenshots_"))
DB_PATH = TMP_DIR / "screenshots.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
db_connection.engine = engine
db_connection.SessionLocal = session_factory
db_connection.DB_PATH = str(DB_PATH)

from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.connection import init_db
from app.database.seed import seed_initial_data
from app.models.role import Role
from app.models.user import User

# Pin the look of the published screenshots so they don't depend on
# whoever runs this script. Both are in-memory replacements for this
# process only - set_dark_mode(False) would instead overwrite the
# runner's own saved preference in the registry.
# - Light mode: is_dark_mode() reads a per-machine QSettings value.
#   Patched on the module BEFORE app.ui.main_window/login_bridge are
#   imported, since they bind the name at import time.
# - Device label: the sidebar shows platform.node(), i.e. the real
#   hostname of whatever PC ran this, which has no place in docs.
import platform

import app.ui.theme as theme

theme.is_dark_mode = lambda: False
platform.node = lambda: "COUNTER-PC"

from app.ui.main_window import AppController

OUT_DIR = ROOT / "docs" / "screenshots"


def grab(widget, name: str, size=(1440, 860)) -> None:
    """Login is QML (QQuickWidget hosting LoginScreen.qml), not a plain
    widget tree - its first frame is rendered by the Qt Quick scenegraph
    on its own render loop, not the ordinary widget paint cycle, so a
    handful of processEvents() calls (enough for every plain-QWidget
    screen in this app) can return before anything has actually been
    rasterized into its backing store, and grab() then captures a blank
    frame. Found 2026-09-23 regenerating these screenshots - login.png
    came back solid pale grey, main-window.png (plain widgets) was fine
    on the very same run. Looping processEvents() for up to ~2 seconds,
    checking after each pass, gives the QML engine time to actually
    finish loading/compiling/rendering the scene before grab() runs.
    """
    import time

    widget.resize(*size)
    widget.show()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    pixmap = widget.grab()
    pixmap.save(str(OUT_DIR / name))
    widget.hide()
    print(f"Saved {name} ({pixmap.width()}x{pixmap.height()})")


def seed_manager(session_factory) -> None:
    """A Manager login, not admin: admin is seeded with
    must_change_password=True (a known, publicly-committed dev password
    that must be rotated before real use), which would show a
    change-password interstitial instead of the dashboard this screenshot
    is meant to show. A Manager also gives a more representative
    day-to-day view than the every-permission Admin/Owner screens would.
    """
    session = session_factory()
    try:
        manager_role = session.query(Role).filter_by(name=UserRole.MANAGER.value).first()
        now = datetime.now(timezone.utc)
        session.add(
            User(
                username="manager1",
                email="manager1@example.com",
                password_hash=hash_password("Passw0rd!"),
                first_name="Manager",
                last_name="One",
                is_active=True,
                is_locked=False,
                failed_attempts=0,
                must_change_password=False,
                role=manager_role,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    finally:
        session.close()


def main() -> None:
    init_db()
    seed_initial_data()
    seed_manager(session_factory)

    # launch_app() applies the app-wide QSS before creating any window;
    # without this every screen renders in Qt's unstyled default look
    # (found 2026-09-23: main-window.png came out as bare dark widgets).
    theme.apply_theme(app)
    controller = AppController()
    controller.start()
    grab(controller.login_window, "login.png", size=(1220, 730))

    success, user_data, error = controller._auth_service.authenticate(
        "manager1", "Passw0rd!", device_info="screenshot-capture"
    )
    if not success:
        raise SystemExit(f"Could not log in as manager1 for capture: {error}")

    controller._show_main_window(user_data)
    # The alert strip/badge only refreshes on the session timer's own
    # tick (deliberately, not on startup - see _check_session's comment
    # in main_window.py), which is minutes away in a real run. Trigger it
    # once directly so the screenshot shows real "All clear"/alert-count
    # content instead of the strip's permanent "Checking for alerts..."
    # loading state.
    controller.main_window.refresh_alert_badge()
    grab(controller.main_window, "main-window.png", size=(1440, 860))


if __name__ == "__main__":
    main()
