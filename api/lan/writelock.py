"""One writer at a time, and the audit chain stays one line.

AuditLogRepository.record reads the newest audit row and then appends a row chained to it. Two requests doing that at the same time
could both chain onto the same predecessor. On the Main PC every transaction therefore takes ONE lock before its first write and
gives it back at commit/rollback. The lock is always taken BEFORE SQLite's own write lock, so the two can never wait on each other.
Reads that never write are not affected and run in parallel (WAL).

AuditLogRepository is not changed. install() attaches listeners to the one engine and wraps `record` so it takes the lock before
it stamps its time (see _serialise_audit_records). Engines without install() are not affected at all.
"""

import threading

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

WAIT_SECONDS = 30
_WRITE_WORDS = ("INSERT", "UPDATE", "DELETE", "REPLACE")


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.held: set[int] = set()
        self.guard = threading.Lock()

    def take(self, raw_id: int, what: str) -> None:
        with self.guard:
            if raw_id in self.held:
                return
        if not self.lock.acquire(timeout=WAIT_SECONDS):
            raise OperationalError(what, {}, Exception("The Main PC is busy saving other work. Try again."))
        with self.guard:
            self.held.add(raw_id)

    def release(self, raw_id: int) -> None:
        with self.guard:
            if raw_id in self.held:
                self.held.discard(raw_id)
                self.lock.release()


_states: dict = {}  # engine -> _State


def _raw_id(conn) -> int:
    return id(conn.connection.dbapi_connection)


def _wants_lock(statement: str) -> bool:
    return statement.lstrip()[:7].upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))


def _serialise_audit_records() -> None:
    """AuditLogRepository.record stamps created_at BEFORE it reads the newest entry. If the lock were only taken at that read, a
    request could stamp its time, wait, and then chain onto an entry with a LATER time: the chain would be intact by hash but
    out of time order, and verify_chain (which sorts by time) would call it broken. So the lock is taken before record() starts.
    The repository's code is untouched; the method is wrapped, and only for engines passed to install()."""
    from app.repositories.audit_log_repository import AuditLogRepository

    if getattr(AuditLogRepository.record, "_pperp_serialised", False):
        return
    original = AuditLogRepository.record

    def record(self, *args, **kwargs):
        state = _states.get(self._session.get_bind())
        if state is not None:
            conn = self._session.connection()
            state.take(_raw_id(conn), "audit")
        return original(self, *args, **kwargs)

    record._pperp_serialised = True  # type: ignore[attr-defined]
    AuditLogRepository.record = record  # type: ignore[method-assign]


def install(engine) -> None:
    engine.dispose()  # connections opened earlier would not get the busy timeout below
    state = _states[engine] = _State()
    _serialise_audit_records()

    @event.listens_for(engine, "before_cursor_execute")
    def acquire(conn, cursor, statement, parameters, context, executemany):
        if _wants_lock(statement):
            state.take(_raw_id(conn), statement)

    # Give the lock back only AFTER SQLite has really committed or rolled back. (SQLAlchemy's own "commit" event fires BEFORE the
    # driver's commit, which would let the next writer read the old newest audit row.)
    dialect = engine.dialect
    for name in ("do_commit", "do_rollback"):
        original = getattr(dialect, name)

        def wrapped(dbapi_connection, _original=original):
            try:
                _original(dbapi_connection)
            finally:
                state.release(id(dbapi_connection))

        setattr(dialect, name, wrapped)

    @event.listens_for(engine.pool, "reset")
    def on_reset(dbapi_connection, connection_record, reset_state):  # backstop: a connection returned with the lock still held
        state.release(id(dbapi_connection))

    @event.listens_for(engine, "connect")
    def pragmas(dbapi_connection, record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()
