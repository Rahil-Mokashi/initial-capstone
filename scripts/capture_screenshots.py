"""Regenerate docs/screenshots/*.png by rendering the real Qt widgets directly.

Uses QWidget.grab(), which renders the widget's own backing store into a
QPixmap - it does not depend on OS window focus, stacking order, or a
screen capture of any kind. The offscreen QPA platform is deliberately NOT
used here since it lacks real system font rendering on this machine.
Run with: python scripts/capture_screenshots.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from app.ui.main_window import AppController

OUT_DIR = ROOT / "docs" / "screenshots"


def grab(widget, name: str, size=(1440, 860)) -> None:
    widget.resize(*size)
    widget.show()
    for _ in range(5):
        app.processEvents()
    pixmap = widget.grab()
    pixmap.save(str(OUT_DIR / name))
    widget.hide()
    print(f"Saved {name} ({pixmap.width()}x{pixmap.height()})")


def main() -> None:
    controller = AppController()
    controller.start()
    grab(controller.login_window, "login.png", size=(1220, 730))

    success, user_data, error = controller._auth_service.authenticate(
        "manager1", "Passw0rd!", device_info="screenshot-capture"
    )
    if not success:
        raise SystemExit(f"Could not log in as manager1 for capture: {error}")

    controller._show_main_window(user_data)
    grab(controller.main_window, "main-window.png", size=(1440, 860))


if __name__ == "__main__":
    main()
