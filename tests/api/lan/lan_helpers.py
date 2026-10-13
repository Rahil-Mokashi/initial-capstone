"""A real Main PC on loopback with real mutual TLS, and a Python reference of what the Electron client does to enrol."""

import hashlib
import secrets
import socket
import ssl
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from api.lan.config import LanConfig
from api.lan.devices import proof, pairing_key
from api.lan.pki import Pki
from api.lan import server as lan_server

ADDRESS = "127.0.0.1"


def free_port() -> int:
    with socket.socket() as s:
        s.bind((ADDRESS, 0))
        return s.getsockname()[1]


def make_config(**over) -> LanConfig:
    base = dict(mode="main", bind_address=ADDRESS, port=free_port(), pairing_port=free_port(), allowed_subnets=["127.0.0.0/16"])
    base.update(over)
    return LanConfig(**base)


class MainPc:
    """Starts the guarded API and the pairing listener the same way run_main does, minus the OS-level steps."""

    def __init__(self, folder: Path, session_factory, config: LanConfig, protector):
        self.config, self.folder = config, folder
        from api.lan import writelock

        writelock.install(session_factory.kw["bind"])  # what run_main does on the real engine
        self.pki = Pki(folder / "pki", protector)
        self.pki.ensure(config)
        self.lan = lan_server.build_lan(config, self.pki, session_factory)
        self.blocks: list[tuple[str, str, str]] = []
        self.app = lan_server.build_main_asgi(config, self.lan, session_factory, on_block=lambda *a: (self.blocks.append(a), self.lan.record_block(*a)))
        self.server = uvicorn.Server(lan_server.main_uvicorn_config(self.app, config, self.pki))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(200):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("test Main PC did not start")

    def __exit__(self, *exc):
        self.lan.listener.stop()
        self.server.should_exit = True
        self.thread.join(10)

    @property
    def base(self) -> str:
        return f"https://{ADDRESS}:{self.config.port}"

    # --- a device, the way the Electron client does it
    def enrol(self, name: str, code: str, *, tamper_fingerprint: bool = False) -> dict:
        pair = f"https://{ADDRESS}:{self.config.pairing_port}"
        with httpx.Client(verify=False, timeout=10) as c:
            ca = c.get(f"{pair}/pair/ca").json()
        fp = ca["fingerprint"] if not tamper_fingerprint else "0" * 64
        nonce = secrets.token_hex(16)
        key = pairing_key(code)
        body = {"device_name": name, "nonce": nonce, "ca_fingerprint": fp, "proof": proof(key, "enrol", name, nonce, fp)}
        ca_file = self.folder / f"seen-ca-{secrets.token_hex(3)}.pem"
        ca_file.write_text(ca["ca_pem"])
        with httpx.Client(verify=str(ca_file), timeout=10) as c:
            r = c.post(f"{pair}/pair/enrol", json=body)
        out = {"status": r.status_code, "ca_pem": ca["ca_pem"], "nonce": nonce, "fingerprint": fp, "key": key}
        if r.status_code == 200:
            out.update(r.json())
        return out

    def client(self, device: dict, *, with_token: bool = True, **kw) -> httpx.Client:
        d = self.folder / f"dev-{secrets.token_hex(3)}"
        d.mkdir()
        (d / "ca.pem").write_text(device["ca_pem"])
        (d / "c.pem").write_text(device["cert_pem"])
        (d / "k.pem").write_text(device["key_pem"])
        headers = {"X-Device-Token": device["token"]} if with_token else {}
        return httpx.Client(base_url=self.base, verify=client_context(d / "ca.pem", d / "c.pem", d / "k.pem"), headers=headers, timeout=15, **kw)


def client_context(ca: Path, cert: Path, key: Path) -> ssl.SSLContext:
    """httpx 0.28 ignores cert= when verify= is a path, so build the context ourselves."""
    ctx = ssl.create_default_context(cafile=str(ca))
    ctx.load_cert_chain(str(cert), str(key))
    return ctx


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
