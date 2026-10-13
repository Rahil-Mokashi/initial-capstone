"""Folder access lists: keys, the database and backups are readable by SYSTEM, Administrators and the running account only."""

import subprocess
import sys
from pathlib import Path

from api.lan.config import LanConfigError

SYSTEM, ADMINS = "*S-1-5-18", "*S-1-5-32-544"
# Well-known groups that mean "other people on this PC".
BROAD = ("Everyone", "BUILTIN\\Users", "NT AUTHORITY\\Authenticated Users", "BUILTIN\\Guests")


def _run(args: list[str]) -> str:
    done = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise LanConfigError(f"{args[0]} failed: {(done.stderr or done.stdout).strip()[:200]}")
    return done.stdout


def _current_sid() -> str:
    out = _run(["whoami", "/user", "/fo", "csv", "/nh"])
    return "*" + out.strip().split(",")[-1].strip().strip('"')


def harden(path: Path) -> None:
    """Remove inherited access and leave SYSTEM, Administrators and the current account. Raises if it cannot."""
    if sys.platform != "win32":
        raise LanConfigError("Folder protection is implemented for Windows only.")
    path.mkdir(parents=True, exist_ok=True)
    _run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{SYSTEM}:(OI)(CI)F", f"{ADMINS}:(OI)(CI)F", f"{_current_sid()}:(OI)(CI)F"])
    if not is_hardened(path):
        raise LanConfigError(f"Could not restrict access to {path}")


def is_hardened(path: Path) -> bool:
    if sys.platform != "win32" or not path.exists():
        return False
    listing = _run(["icacls", str(path)]).lower()
    return not any(name.lower() in listing for name in BROAD)
