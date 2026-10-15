"""Small secrets kept on the Main PC outside the database (today: the mail password), protected by Windows DPAPI.

The file holds only the protected blob; it is useless on any other computer or account. Never logged, never returned by the API.
"""

from pathlib import Path
from typing import Optional

from api.lan.config import LanConfigError, lan_dir
from api.lan.pki import DpapiProtector, Protector


class SecretStore:
    def __init__(self, folder: Optional[Path] = None, protector: Optional[Protector] = None, allow_insecure: bool = False):
        self._dir = Path(folder) if folder else lan_dir()
        self._protector = protector or DpapiProtector()
        self._allow_insecure = allow_insecure  # tests only

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}.secret"

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def set(self, name: str, value: str) -> None:
        if not self._protector.secure and not self._allow_insecure:
            raise LanConfigError("This computer cannot protect a password (Windows data protection is unavailable), so it will not be saved.")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(name).write_bytes(self._protector.protect(value.encode("utf-8")))

    def get(self, name: str) -> Optional[str]:
        path = self._path(name)
        if not path.exists():
            return None
        try:
            return self._protector.unprotect(path.read_bytes()).decode("utf-8")
        except Exception:  # noqa: BLE001 - a blob from another PC or account reads as "not set"
            return None

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)
