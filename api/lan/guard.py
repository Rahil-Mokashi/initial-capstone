"""The Main PC's front door. Pure ASGI so it also sees streams (server-sent events) and bodies as they arrive.

Order, outermost first: network allow-list -> Host check -> body size limit -> device token -> per-device rate limit -> request time limit.
Anything refused answers with the standard error envelope and never reveals which check failed beyond a short code.
"""

import asyncio
import ipaddress
import json
import time
from collections import defaultdict, deque
from typing import Callable, Iterable, Optional

from api.lan.devices import DeviceService

TOKEN_HEADER = b"x-device-token"
REQUEST_SECONDS = 120
SENSITIVE_PATHS = ("/api/auth/login", "/api/auth/forgot-password", "/api/auth/reauthenticate")
SENSITIVE_PER_MINUTE = 10


def _envelope(status: int, code: str, message: str) -> tuple[list, bytes]:
    body = json.dumps({"error": {"code": code, "message": message, "details": {}}}).encode()
    return [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")], body


async def _send_error(send, status: int, code: str, message: str) -> None:
    headers, body = _envelope(status, code, message)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class LanGuard:
    def __init__(
        self,
        app,
        devices: DeviceService,
        allowed_subnets: Iterable[str],
        allowed_hosts: Iterable[str],
        max_body_bytes: int,
        requests_per_minute: int,
        on_block: Callable[[str, str, str], None] = lambda kind, ip, detail: None,
    ):
        self.app = app
        self.devices = devices
        self.nets = [ipaddress.ip_network(n) for n in allowed_subnets]
        self.hosts = {h.lower() for h in allowed_hosts}
        self.max_body = max_body_bytes
        self.rpm = requests_per_minute
        self._on_block = on_block
        self._hits: dict[str, deque] = defaultdict(deque)

    def on_block(self, kind: str, ip: str, detail: str) -> None:
        """Audit/log a refusal off the event loop so a slow disk never delays the answer."""
        asyncio.get_running_loop().run_in_executor(None, self._on_block, kind, ip, detail)

    def _ip_allowed(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self.nets)

    def _rate_ok(self, key: str, limit: Optional[int] = None) -> bool:
        now, window = time.monotonic(), self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= (limit or self.rpm):
            return False
        window.append(now)
        return True

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan passes; websockets are not used
            if scope["type"] == "lifespan":
                return await self.app(scope, receive, send)
            return
        ip = (scope.get("client") or ("", 0))[0]
        if not self._ip_allowed(ip):
            self.on_block("network", ip, "outside the allowed networks")
            return await _send_error(send, 403, "network_not_allowed", "This network address may not use the Main PC.")
        headers = {k.lower(): v for k, v in scope["headers"]}
        host = headers.get(b"host", b"").decode("latin1").lower()
        if host.rsplit(":", 1)[0].strip("[]") not in self.hosts:
            self.on_block("host", ip, "unexpected Host header")
            return await _send_error(send, 400, "bad_host", "Unexpected host name.")
        if b"transfer-encoding" in headers:  # sizes must be declared up front so they can be limited
            return await _send_error(send, 411, "length_required", "Send the size of the request.")
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_body):
            return await _send_error(send, 413, "request_too_large", "That request is too large.")
        token = headers.get(TOKEN_HEADER, b"").decode("latin1")
        device = await asyncio.to_thread(self.devices.recognise, token, ip) if token else None
        if device is None:
            self.on_block("device", ip, "unknown or removed device")
            return await _send_error(send, 401, "device_not_recognised", "This PC is not enrolled, or was removed, on the Main PC.")
        if not self._rate_ok(device.id):
            return await _send_error(send, 429, "too_many_requests", "Too many requests from this PC. Wait a moment.")
        if scope["path"] in SENSITIVE_PATHS and not self._rate_ok(f"{device.id}:{scope['path']}", SENSITIVE_PER_MINUTE):
            self.on_block("login_rate", ip, f"too many sign-in attempts from {device.name}")
            return await _send_error(send, 429, "too_many_requests", "Too many sign-in attempts from this PC. Wait a minute.")
        scope["pperp_device"] = {"id": device.id, "name": device.name, "ip": ip}

        streaming = scope["path"].startswith("/api/events")
        started = False

        async def tracking_send(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            if streaming:
                await self.app(scope, receive, tracking_send)
            else:
                await asyncio.wait_for(self.app(scope, receive, tracking_send), REQUEST_SECONDS)
        except asyncio.TimeoutError:
            if not started:
                await _send_error(send, 504, "request_timeout", "The Main PC took too long to answer.")
