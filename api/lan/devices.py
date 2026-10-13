"""Enrolling PCs, recognising them on every request, and revoking them.

All outcomes go to the existing audit log (AuditLogRepository.record) with the device name and IP.
"""

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.lan_device import LanDevice
from app.repositories.audit_log_repository import AuditLogRepository

from api.lan.pki import Pki

# No 0/O/1/I/L: the code is read aloud and typed on a different PC.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10
CODE_MINUTES = 10
MAX_WRONG_TRIES = 5
PBKDF2_ROUNDS = 200_000
TOUCH_SECONDS = 60


def normalise_code(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())


def pairing_key(code: str) -> bytes:
    """Slows down guessing of the short code from a captured proof."""
    return hashlib.pbkdf2_hmac("sha256", normalise_code(code).encode(), b"pperp-pairing-v1", PBKDF2_ROUNDS)


def proof(key: bytes, *parts: str) -> str:
    return hmac.new(key, "|".join(parts).encode(), hashlib.sha256).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class PairingState:
    key: bytes
    created_by_id: str
    expires_at: float
    wrong_tries: int = 0


class PairingManager:
    """At most one live pairing code. In memory only: a restart cancels it."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._state: Optional[PairingState] = None

    def create(self, created_by_id: str) -> tuple[str, int]:
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        with self._lock:
            self._state = PairingState(pairing_key(code), created_by_id, self._clock() + CODE_MINUTES * 60)
        return f"{code[:5]}-{code[5:]}", CODE_MINUTES

    def active(self) -> bool:
        with self._lock:
            return self._state is not None and self._clock() < self._state.expires_at

    def cancel(self) -> None:
        with self._lock:
            self._state = None

    def consume(self, device_name: str, nonce: str, ca_fingerprint: str, client_proof: str) -> Optional[tuple[bytes, str]]:
        """Return (key, created_by_id) when the proof is right, and use the code up. A wrong proof counts against the code."""
        with self._lock:
            st = self._state
            if st is None or self._clock() >= st.expires_at:
                self._state = None
                return None
            expected = proof(st.key, "enrol", device_name, nonce, ca_fingerprint)
            if not hmac.compare_digest(expected, client_proof):
                st.wrong_tries += 1
                if st.wrong_tries >= MAX_WRONG_TRIES:
                    self._state = None
                return None
            self._state = None  # single use
            return st.key, st.created_by_id


@dataclass
class Enrolment:
    device_id: str
    name: str
    cert_pem: str
    key_pem: str
    token: str
    server_proof: str


class DeviceService:
    def __init__(self, session_factory: Callable[[], Session], pki: Pki, pairing: PairingManager):
        self._sf = session_factory
        self.pki = pki
        self.pairing = pairing
        self._touched: dict[str, float] = {}

    # ---- enrolment
    def enrol(self, device_name: str, nonce: str, ca_fingerprint: str, client_proof: str, ip: str) -> Optional[Enrolment]:
        name = " ".join(device_name.split())[:80]
        if not name or not nonce:
            return None
        # The fingerprint is OUR authority's, never the one the caller claims: a machine in the middle that showed the
        # client its own authority made the client hash a different fingerprint, so its proof fails here.
        ca_fingerprint = self.pki.ca_fingerprint()
        used = self.pairing.consume(name, nonce, ca_fingerprint, client_proof)
        if used is None:
            self._audit("device_enrol_refused", None, None, f"Enrolment refused for '{name}' from {ip}", ip)
            return None
        key, created_by = used
        token = secrets.token_hex(32)
        with self._sf() as db:
            device = LanDevice(name=name, cert_serial="pending", cert_fingerprint="pending", token_hash=hash_token(token),
                               enrolled_by_id=created_by, enrolled_ip=ip)
            db.add(device)
            db.flush()
            ident = self.pki.issue_client(name, device.id)
            device.cert_serial, device.cert_fingerprint = ident.serial, ident.fingerprint
            db.commit()
            AuditLogRepository(db).record(
                "device_enrolled", actor_id=created_by, entity_type="LanDevice", entity_id=device.id,
                description=f"Device '{name}' enrolled from {ip}", device_info=f"{name} ({ip})",
            )
            return Enrolment(device.id, name, ident.cert_pem.decode(), ident.key_pem.decode(), token,
                             proof(key, "ok", nonce, ca_fingerprint, token))

    def enrol_local(self, name: str, by_user_id: str, ip: str = "console") -> Enrolment:
        """Console enrolment by someone who can already read the Main PC's key folder (an Administrator at the machine).
        Used for the Main PC's own window and when no owner can sign in anywhere. No pairing code; audited as such."""
        token = secrets.token_hex(32)
        with self._sf() as db:
            device = LanDevice(name=name[:80], cert_serial="pending", cert_fingerprint="pending", token_hash=hash_token(token),
                               enrolled_by_id=by_user_id, enrolled_ip=ip)
            db.add(device)
            db.flush()
            ident = self.pki.issue_client(name, device.id)
            device.cert_serial, device.cert_fingerprint = ident.serial, ident.fingerprint
            db.commit()
            AuditLogRepository(db).record(
                "device_enrolled_by_console", actor_id=by_user_id, entity_type="LanDevice", entity_id=device.id,
                description=f"Device '{device.name}' enrolled at the Main PC console", device_info=f"{device.name} ({ip})",
            )
            return Enrolment(device.id, device.name, ident.cert_pem.decode(), ident.key_pem.decode(), token, "")

    # ---- every request
    def recognise(self, token: str, ip: str) -> Optional[LanDevice]:
        """The active device owning this token, or None (unknown or revoked)."""
        with self._sf() as db:
            device = db.query(LanDevice).filter_by(token_hash=hash_token(token)).first()
            if device is None or device.revoked_at is not None:
                return None
            now = time.monotonic()
            if now - self._touched.get(device.id, -1e9) >= TOUCH_SECONDS or device.last_ip != ip:
                self._touched[device.id] = now
                device.last_seen_at, device.last_ip = datetime.now(timezone.utc), ip
                db.commit()
            db.expunge(device)
            return device

    # ---- owner screen
    def list_devices(self) -> list[LanDevice]:
        with self._sf() as db:
            rows = db.query(LanDevice).order_by(LanDevice.enrolled_at.desc()).all()
            db.expunge_all()
            return rows

    def revoke(self, device_id: str, by_user_id: str, reason: str) -> LanDevice:
        reason = reason.strip() or "No reason given"  # a reason is optional everywhere in the app
        with self._sf() as db:
            device = db.get(LanDevice, device_id)
            if device is None:
                raise NotFoundError("Device not found.")
            if device.revoked_at is None:
                device.revoked_at, device.revoked_by_id, device.revoke_reason = datetime.now(timezone.utc), by_user_id, reason[:200]
                db.commit()
                AuditLogRepository(db).record(
                    "device_revoked", actor_id=by_user_id, entity_type="LanDevice", entity_id=device.id,
                    description=f"Device '{device.name}' removed: {reason[:200]}",
                )
            self.write_crl(db)
            db.expunge(device)
            return device

    def write_crl(self, db: Session) -> None:
        rows = db.query(LanDevice).filter(LanDevice.revoked_at.isnot(None)).all()
        self.pki.write_crl([(r.cert_serial, r.revoked_at) for r in rows])

    def _audit(self, event: str, actor: Optional[str], entity_id: Optional[str], text: str, ip: str) -> None:
        with self._sf() as db:
            AuditLogRepository(db).record(event, actor_id=actor, entity_type="LanDevice", entity_id=entity_id,
                                          description=text, device_info=ip)
