"""Main PC mode: the guarded, mutually authenticated listener, and the short-lived enrolment listener.

`run_main()` refuses to start (raises LanConfigError) unless every protection could be put in place. There is no plain-HTTP fallback.
"""

import ipaddress
import json
import os
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.lan import fs_security
from api.lan.config import LanConfig, LanConfigError, lan_dir, load
from api.lan.devices import DeviceService, PairingManager
from api.lan.guard import LanGuard
from api.lan.live import EventHub, ResourceVersions
from api.lan.pki import DpapiProtector, Pki, Protector


class _Throttle:
    """Same-address brake for the enrolment listener."""

    def __init__(self, limit: int, seconds: int = 60):
        self.limit, self.seconds, self.hits = limit, seconds, {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self.hits.get(key, []) if now - t < self.seconds]
        if len(recent) >= self.limit:
            self.hits[key] = recent
            return False
        recent.append(now)
        self.hits[key] = recent
        return True


class EnrolIn(BaseModel):
    device_name: str = Field(min_length=1, max_length=80)
    nonce: str = Field(min_length=16, max_length=64, pattern=r"^[0-9a-f]+$")
    ca_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")
    proof: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")


def build_pairing_app(config: LanConfig, devices: DeviceService) -> FastAPI:
    """Two routes only. Reachable only while a pairing code is live (see PairingListener)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    nets = [ipaddress.ip_network(n) for n in config.allowed_subnets]
    throttle = _Throttle(30)

    @app.middleware("http")
    async def gate(request: Request, call_next):
        ip = request.client.host if request.client else ""
        try:
            allowed = any(ipaddress.ip_address(ip) in n for n in nets)
        except ValueError:
            allowed = False
        if not allowed or not throttle.allow(ip):
            return JSONResponse({"error": {"code": "refused", "message": "Refused."}}, status_code=403)
        return await call_next(request)

    @app.get("/pair/ca")
    def ca():
        return {"ca_pem": devices.pki.ca_pem().decode(), "fingerprint": devices.pki.ca_fingerprint()}

    @app.post("/pair/enrol")
    def enrol(body: EnrolIn, request: Request):
        result = devices.enrol(body.device_name, body.nonce, body.ca_fingerprint, body.proof, request.client.host)
        if result is None:  # one message for every cause: wrong code, expired, used, bad fingerprint
            return JSONResponse({"error": {"code": "pairing_failed", "message": "Pairing failed. Ask the owner for a new code."}}, status_code=403)
        return {"device_id": result.device_id, "cert_pem": result.cert_pem, "key_pem": result.key_pem, "token": result.token,
                "server_proof": result.server_proof}

    return app


class PairingListener:
    """The enrolment port exists only while a pairing code is live."""

    def __init__(self, config: LanConfig, pki: Pki, devices: DeviceService):
        self.config, self.pki, self.devices = config, pki, devices
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.running():
                return
            app = build_pairing_app(self.config, self.devices)
            pki = self.pki
            cfg = uvicorn.Config(app, host=self.config.bind_address, port=self.config.pairing_port, log_level="warning", access_log=False,
                                 ssl_context_factory=lambda c, default: pki.server_only_context(), server_header=False,
                                 timeout_keep_alive=5, http="h11", h11_max_incomplete_event_size=8192)
            self._server = uvicorn.Server(cfg)
            self._thread = threading.Thread(target=self._server.run, name="pairing-listener", daemon=True)
            self._thread.start()
            for _ in range(100):
                if self._server.started:
                    break
                time.sleep(0.05)
            else:
                raise LanConfigError("The enrolment port could not be opened.")
            threading.Thread(target=self._watch, name="pairing-watch", daemon=True).start()

    def _watch(self) -> None:
        while self.running():
            if self.devices.pairing.active():
                time.sleep(0.5)
                continue
            time.sleep(1.5)  # let an answer in flight finish
            if not self.devices.pairing.active():  # a NEW code may have been asked for meanwhile: then the door stays open
                self.stop()
                return

    def stop(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.should_exit = True
            if self._thread is not None and self._thread is not threading.current_thread():
                self._thread.join(5)
            self._server = self._thread = None


@dataclass
class LanContext:
    """What the API app needs to know when it runs as a Main PC (api.app.create_app(lan=...))."""

    config: LanConfig
    devices: DeviceService
    listener: PairingListener
    allowed_hosts: list[str] = field(default_factory=list)
    session_factory: Optional[Callable] = None
    _blocked: dict = field(default_factory=dict)
    hub: EventHub = field(default_factory=EventHub)
    secrets: Optional[object] = None

    def record_block(self, kind: str, ip: str, detail: str) -> None:
        """Audit a refusal, at most once per kind and address every five minutes (a flood must not flood the audit log)."""
        now = time.monotonic()
        if now - self._blocked.get((kind, ip), -1e9) < 300 or self.session_factory is None:
            return
        self._blocked[(kind, ip)] = now
        from app.repositories.audit_log_repository import AuditLogRepository

        with self.session_factory() as db:
            AuditLogRepository(db).record(f"lan_blocked_{kind}", entity_type="LanDevice", description=f"Refused {ip}: {detail}", device_info=ip)

    def start_pairing(self, user_id: str) -> tuple[str, int]:
        code, minutes = self.devices.pairing.create(user_id)
        self.listener.start()
        return code, minutes

    def cancel_pairing(self) -> None:
        self.devices.pairing.cancel()
        self.listener.stop()

    def describe(self, request: Request) -> str:
        from api.deps import device_name

        return device_name(request)


def allowed_hosts_for(config: LanConfig) -> list[str]:
    return [config.bind_address, *config.server_names]


def build_lan(config: LanConfig, pki: Pki, session_factory: Callable, secrets=None) -> LanContext:
    devices = DeviceService(session_factory, pki, PairingManager())
    return LanContext(config, devices, PairingListener(config, pki, devices), allowed_hosts_for(config), session_factory, secrets=secrets)


def build_main_asgi(config: LanConfig, lan: LanContext, session_factory: Callable, web_dir: Optional[Path] = None,
                    on_block: Optional[Callable[[str, str, str], None]] = None):
    """The API behind the guard. Used by run_main and by the tests."""
    from api.app import create_app

    inner = create_app(secrets.token_hex(16), session_factory=session_factory, web_dir=web_dir, lan=lan)
    return LanGuard(ResourceVersions(inner, session_factory, lan.hub), lan.devices, config.allowed_subnets, lan.allowed_hosts, config.max_body_bytes, config.requests_per_minute,
                    on_block or lan.record_block)


def main_uvicorn_config(app, config: LanConfig, pki: Pki) -> uvicorn.Config:
    return uvicorn.Config(
        app, host=config.bind_address, port=config.port, log_level="warning", access_log=False, server_header=False,
        ssl_context_factory=lambda c, default: pki.mutual_tls_context(),
        timeout_keep_alive=5, http="h11", h11_max_incomplete_event_size=16384, limit_concurrency=200, timeout_graceful_shutdown=10,
    )


def check_address_is_ours(address: str) -> None:
    """Binding fails anyway for a foreign address, but say it in words."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((address, 0))
    except OSError:
        raise LanConfigError(f"{address} is not an address of this computer. Check the Main PC's network address.")
    finally:
        probe.close()


def prepare(config: LanConfig, protector: Protector, folder: Optional[Path] = None) -> Pki:
    """Every protection a Main PC needs, or LanConfigError. Nothing is opened yet."""
    config.validate_for_main()
    if not protector.secure:
        raise LanConfigError("Keys cannot be protected on this computer (Windows DPAPI is needed); the Main PC will not start.")
    check_address_is_ours(config.bind_address)
    folder = folder or lan_dir()
    fs_security.harden(folder)
    from app.database import connection

    db_dir = Path(os.path.abspath(connection.DB_PATH)).parent
    fs_security.harden(db_dir)  # the database and its backups folder
    pki = Pki(folder / "pki", protector)
    pki.ensure(config)
    return pki


def run_main(protector: Optional[Protector] = None) -> int:
    from app.core.logging import logger, setup_logging
    from app.database import connection
    from app.main import _initialize_database

    setup_logging()
    config = load()
    pki = prepare(config, protector or DpapiProtector())
    _initialize_database()
    from api.lan.writelock import install as install_write_lock

    install_write_lock(connection.engine)
    from api.lan.backup_scheduler import BackupScheduler
    from api.lan.mail_scheduler import MailScheduler
    from api.lan.secrets_store import SecretStore
    from api.services import Services

    secrets = SecretStore(lan_dir(), protector or DpapiProtector())
    lan = build_lan(config, pki, connection.SessionLocal, secrets)

    def make_services():
        db = connection.SessionLocal()
        return Services(db, 8, secrets), db.close

    schedulers = [BackupScheduler(make_services), MailScheduler(make_services)]
    for scheduler in schedulers:
        scheduler.start()
    web_dir = os.environ.get("PPERP_WEB_DIR")
    app = build_main_asgi(config, lan, connection.SessionLocal, Path(web_dir) if web_dir else None)
    server = uvicorn.Server(main_uvicorn_config(app, config, pki))
    logger.info("Main PC listening on %s:%s", config.bind_address, config.port)
    try:
        server.run()
    finally:
        for scheduler in schedulers:
            scheduler.stop()
        lan.listener.stop()
        with connection.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.engine.dispose()
        logger.info("Main PC stopped cleanly")
    return 0
