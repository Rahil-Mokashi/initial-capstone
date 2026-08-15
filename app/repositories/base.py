from typing import Generic, Type, TypeVar
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

ModelType = TypeVar("ModelType")


def safe_commit(session: Session) -> None:
    """Commit the session, rolling back cleanly on failure.

    A failed commit (e.g. a unique or foreign-key constraint violation)
    leaves a SQLAlchemy session's transaction aborted. Every session in
    this app is long-lived — one per login, shared across many service
    calls — so without an explicit rollback here, the *next* unrelated
    operation on that session would fail too, with a confusing
    "this transaction is inactive" error masking the real cause. Every
    repository's add/update should commit through this helper rather
    than calling session.commit() directly.
    """
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
