from contextlib import contextmanager
from typing import Generic, Iterator, Type, TypeVar

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

ModelType = TypeVar("ModelType")

# Attribute stashed on the Session itself (rather than a module-level
# counter or a ContextVar) to track how deeply nested the current unit
# of work is. It has to live on the session because the depth is a
# property of *that* session's transaction — a future change to
# session-per-operation, or a background worker thread with its own
# Session (both are on the roadmap), must not see another session's
# depth and silently skip its own commit.
_UOW_DEPTH_ATTR = "_petrolpump_uow_depth"


def _uow_depth(session: Session) -> int:
    return getattr(session, _UOW_DEPTH_ATTR, 0)


def session_for(repository) -> Session:
    """Return the Session a repository is bound to.

    Services hold repositories, not sessions, but a service method needs
    the session to open a unit of work over the whole operation. Every
    repository in this app stores it as `_session`, so rather than
    scatter that private access across a dozen service constructors it
    is named once, here, as the deliberate convention it is. If
    repositories ever stop sharing that attribute name, this is the
    single place that has to change.
    """
    return repository._session


@contextmanager
def unit_of_work(session: Session) -> Iterator[Session]:
    """Run a whole business operation inside one database transaction.

    CLAUDE.md requires "Always use transactions for financial operations"
    and "Never allow partial financial writes". Before this existed every
    repository committed on its own, so a service method like
    SaleService.create_sale was four or five separate transactions: the
    Sale row, the tank ISSUE transaction plus the tank's stock
    decrement, the Sale's update with the transaction id, and the
    Payment row. A constraint violation, a disk-full or a crash between
    any two of them left the database in a state the business rules say
    is impossible — fuel gone from a tank with no sale accounting for
    it, or a completed sale with no payment record (which then silently
    corrupts shift reconciliation).

    Wrapping a service method in this makes the whole method one
    transaction: everything commits together on a clean exit, and *any*
    exception rolls back every write the method made, not just the last
    one.

    Nesting is safe and deliberate: services call other services
    (SaleService -> TankService -> CreditService), and an inner unit of
    work joins the outer one rather than committing early and breaking
    the outer method's atomicity. Only the outermost block commits.
    """
    if _uow_depth(session) > 0:
        # Already inside an outer unit of work — join it. Do not commit
        # or roll back here; the outermost block owns the transaction.
        setattr(session, _UOW_DEPTH_ATTR, _uow_depth(session) + 1)
        try:
            yield session
        finally:
            setattr(session, _UOW_DEPTH_ATTR, _uow_depth(session) - 1)
        return

    setattr(session, _UOW_DEPTH_ATTR, 1)
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        setattr(session, _UOW_DEPTH_ATTR, 0)


def safe_commit(session: Session) -> None:
    """Persist pending changes, rolling back cleanly on failure.

    Inside a unit_of_work this *flushes* instead of committing. Flushing
    emits the INSERT/UPDATE statements within the caller's open
    transaction, so generated defaults are populated and the rows are
    readable by the rest of the operation — exactly what the repositories
    need for their follow-up session.refresh() — while leaving the
    commit/rollback decision to the unit of work that owns the
    transaction. This is what lets every existing repository keep calling
    safe_commit() unchanged and still become atomic as a group.

    Outside a unit of work the old behaviour is kept: commit, and roll
    back on failure. A failed commit leaves a SQLAlchemy session's
    transaction aborted, and sessions in this app are long-lived (one per
    login, shared across many service calls), so without the rollback the
    *next* unrelated operation would also fail with a confusing
    "this transaction is inactive" error masking the real cause.
    """
    if _uow_depth(session) > 0:
        try:
            session.flush()
        except SQLAlchemyError:
            # Do not roll back here — the unit of work will, and it must
            # unwind the *whole* operation rather than just this write.
            raise
        return

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise


class Repository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: Session):
        self._model = model
        self._session = session

    def get(self, id: str):
        return self._session.get(self._model, id)

    def list(self):
        return self._session.query(self._model).filter_by(is_deleted=False).all()

    def add(self, instance: ModelType):
        self._session.add(instance)
        safe_commit(self._session)
        self._session.refresh(instance)
        return instance

    def update(self, instance: ModelType):
        safe_commit(self._session)
        self._session.refresh(instance)
        return instance

    def delete(self, instance: ModelType):
        instance.is_deleted = True
        return self.update(instance)
