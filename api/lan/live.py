"""Live data on the Main PC: "something changed" pushes, and version numbers for records two people may edit.

Both are plain ASGI wrappers around the API (they sit inside the guard, so the device is already known):

  EventHub        every successful change is announced to the open event streams (GET /api/events, server-sent events).
                  A Client PC that cannot hold the stream open falls back to refreshing every 20 seconds.
  ResourceVersions  a read of /api/<collection>/<id> carries ETag "<n>"; a later change to that record may send If-Match: "<n>".
                  If the record moved on meanwhile the answer is 409 conflict_stale: "Changed by X at HH:MM".
"""

import asyncio
import json
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Optional

from app.core.logging import logger
from app.models.record_version import RecordVersion
from app.models.user import User

RECORD = re.compile(r"^/api/([a-z][a-z-]*)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(/.*)?$")
WRITES = {"POST", "PUT", "PATCH", "DELETE"}
QUIET = ("/api/auth", "/api/system", "/api/events", "/api/checks")  # not "data changed" news
HEARTBEAT_SECONDS = 15
MAX_SUBSCRIBERS = 64


class EventHub:
    """Fan-out of small JSON events. publish() may be called from any thread."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def subscribe(self) -> Optional[asyncio.Queue]:
        with self._lock:
            if len(self._subs) >= MAX_SUBSCRIBERS:
                return None
            self._loop = asyncio.get_running_loop()
            q: asyncio.Queue = asyncio.Queue(maxsize=100)
            self._subs.add(q)
            return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, event: dict) -> None:
        with self._lock:
            subs, loop = list(self._subs), self._loop
        if not subs or loop is None:
            return
        for q in subs:
            def put(queue=q) -> None:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:  # a slow reader just misses a nudge; it refreshes on the next one
                    pass

            loop.call_soon_threadsafe(put)

    @property
    def subscribers(self) -> int:
        return len(self._subs)


async def serve_events(hub: EventHub, receive, send) -> None:
    """The server-sent events response for GET /api/events."""
    q = hub.subscribe()
    if q is None:
        body = b'{"error":{"code":"too_many_streams","message":"Too many open live streams.","details":{}}}'
        await send({"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
        return
    gone = asyncio.Event()

    async def watch_disconnect() -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                gone.set()
                return

    watcher = asyncio.create_task(watch_disconnect())
    try:
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"text/event-stream"), (b"cache-control", b"no-store"), (b"x-accel-buffering", b"no")]})
        await send({"type": "http.response.body", "body": b'retry: 3000\ndata: {"type":"hello"}\n\n', "more_body": True})
        gone_wait = asyncio.create_task(gone.wait())
        while not gone.is_set():
            next_event = asyncio.create_task(q.get())
            done, _ = await asyncio.wait({next_event, gone_wait}, timeout=HEARTBEAT_SECONDS, return_when=asyncio.FIRST_COMPLETED)
            if gone.is_set():
                next_event.cancel()
                break
            if next_event in done:
                chunk = b"data: " + json.dumps(next_event.result(), separators=(",", ":")).encode() + b"\n\n"
            else:
                next_event.cancel()
                chunk = b": beat\n\n"
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        gone_wait.cancel()
    except Exception:  # the client went away mid-write
        pass
    finally:
        hub.unsubscribe(q)
        watcher.cancel()


class ResourceVersions:
    def __init__(self, app, session_factory: Callable, hub: EventHub):
        self.app = app
        self._sf = session_factory
        self.hub = hub
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ---- database work (runs in a worker thread)
    def _version(self, resource: str) -> tuple[int, Optional[str], Optional[datetime]]:
        with self._sf() as db:
            row = db.query(RecordVersion).filter_by(resource=resource).first()
            return (row.version, row.changed_by_name, row.changed_at) if row else (0, None, None)

    def _bump(self, resource: str, token: str) -> int:
        with self._sf() as db:
            user_id, name = self._who(db, token)
            row = db.query(RecordVersion).filter_by(resource=resource).first()
            if row is None:
                row = RecordVersion(resource=resource, version=0)
                db.add(row)
            row.version += 1
            row.changed_by_id, row.changed_by_name, row.changed_at = user_id, name, datetime.now(timezone.utc)
            db.commit()
            return row.version

    @staticmethod
    def _who(db, token: str) -> tuple[Optional[str], Optional[str]]:
        if not token:
            return None, None
        try:
            from app.repositories.user_session_repository import UserSessionRepository

            entry = UserSessionRepository(db).get_by_token(token)
            user = db.get(User, entry.user_id) if entry else None
        except Exception:  # noqa: BLE001 - a name for the message is a nicety, never a reason to fail a save
            user = None
        if user is None:
            return None, None
        return user.id, (f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username)

    # ---- ASGI
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path, method = scope["path"], scope["method"]
        if path == "/api/events" and method == "GET":
            return await serve_events(self.hub, receive, send)
        match = RECORD.match(path)
        headers = {k.lower(): v for k, v in scope["headers"]}
        token = headers.get(b"authorization", b"").decode("latin1").partition(" ")[2].strip()

        if method == "GET" and match and match.group(3) is None:
            resource = f"{match.group(1)}/{match.group(2)}"
            version = (await asyncio.to_thread(self._version, resource))[0]

            async def with_etag(message):
                if message["type"] == "http.response.start" and message["status"] < 400:
                    message = {**message, "headers": list(message["headers"]) + [(b"etag", f'"{version}"'.encode())]}
                await send(message)

            return await self.app(scope, receive, with_etag)

        if method not in WRITES or not path.startswith("/api") or path.startswith(QUIET):
            return await self.app(scope, receive, send)

        resource = f"{match.group(1)}/{match.group(2)}" if match else None
        area = path.split("/")[2] if path.count("/") >= 2 else ""
        if resource is None:
            return await self.app(scope, receive, self._announce(send, area, None, token, None))
        async with self._locks[resource]:
            wanted = headers.get(b"if-match", b"").decode("latin1").strip().strip('"')
            if wanted:
                version, by, at = await asyncio.to_thread(self._version, resource)
                if wanted != str(version):
                    return await self._stale(send, by, at)
            return await self.app(scope, receive, self._announce(send, area, match.group(2), token, resource))

    def _announce(self, send, area: str, record_id: Optional[str], token: str, resource: Optional[str]):
        async def wrapped(message):
            if message["type"] == "http.response.start" and message["status"] < 400:
                extra = []
                if resource:
                    try:
                        version = await asyncio.to_thread(self._bump, resource, token)
                        extra.append((b"etag", f'"{version}"'.encode()))
                    except Exception as exc:  # noqa: BLE001 - the save already succeeded; do not turn it into an error
                        logger.error("Could not count a change to %s: %s", resource, exc)
                self.hub.publish({"type": "changed", "area": area, "id": record_id})
                message = {**message, "headers": list(message["headers"]) + extra}
            await send(message)

        return wrapped

    @staticmethod
    async def _stale(send, by: Optional[str], at: Optional[datetime]) -> None:
        when = at.astimezone().strftime("%H:%M") if at else None
        who = by or "someone else"
        text = f"Changed by {who}" + (f" at {when}" if when else "") + ". Reload to see their change, then make yours again."
        body = json.dumps({"error": {"code": "conflict_stale", "message": text, "details": {"changed_by": by, "changed_at": when}}}).encode()
        await send({"type": "http.response.start", "status": 409, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
