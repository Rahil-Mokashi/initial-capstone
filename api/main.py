"""Sidecar entry point (PyInstaller target).

Electron's main process starts this with:
  PPERP_API_PORT    free port chosen by Electron
  PPERP_API_SECRET  random per-launch secret
  PPERP_WEB_DIR     (optional) folder holding the built web UI
It always binds 127.0.0.1; any other host is refused.
"""

import os
import sys
from pathlib import Path

import uvicorn

BIND_HOST = "127.0.0.1"


def validate_bind(host: str) -> str:
    """The API is for this PC only. Refuse everything but loopback."""
    if host != BIND_HOST:
        raise ValueError(f"The API may only bind to {BIND_HOST}, not {host!r}")
    return host


def build_server(host: str, port: int, secret: str, web_dir: Path | None, **app_kwargs) -> uvicorn.Server:
    from api.app import create_app

    validate_bind(host)
    holder: dict = {}
    app = create_app(secret, web_dir=web_dir, shutdown_callback=lambda: setattr(holder["server"], "should_exit", True), **app_kwargs)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    holder["server"] = server = uvicorn.Server(config)
    return server


def _checkpoint_and_close() -> None:
    """Fold the WAL back into the database file before exit."""
    from app.database import connection

    try:
        with connection.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.engine.dispose()


def _refuse_if_this_pc_is_the_main_pc() -> bool:
    """Two programs writing to one database would break the audit chain: on a Main PC the window must be a Client."""
    try:
        from api.lan.config import LanConfigError, load

        return load().mode == "main"
    except LanConfigError:
        return True  # an unreadable lan.json is never treated as "no Main PC"
    except Exception:
        return False


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "lan":
        from api.lan.cli import run as lan_run

        return lan_run(sys.argv[2:])
    if _refuse_if_this_pc_is_the_main_pc():
        print("This PC is the Main PC. Open the program in Client mode instead of Single PC mode.", file=sys.stderr)
        return 3
    secret = os.environ.get("PPERP_API_SECRET", "")
    port_text = os.environ.get("PPERP_API_PORT", "")
    if not secret or not port_text.isdigit():
        print("PPERP_API_SECRET and PPERP_API_PORT must be set.", file=sys.stderr)
        return 2

    from app.core.logging import logger, setup_logging
    from app.main import _initialize_database

    setup_logging()
    _initialize_database()  # same startup as the Qt app: migrations (with backup) + seed

    web_dir = os.environ.get("PPERP_WEB_DIR")
    server = build_server(BIND_HOST, int(port_text), secret, Path(web_dir) if web_dir else None)
    try:
        server.run()
    finally:
        _checkpoint_and_close()
        logger.info("API sidecar stopped cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
