from typing import Generic, Type, TypeVar
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

ModelType = TypeVar("ModelType")


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
        self._session.commit()
        self._session.refresh(instance)
        return instance

    def update(self, instance: ModelType):
        try:
            self._session.commit()
            self._session.refresh(instance)
            return instance
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def delete(self, instance: ModelType):
        instance.is_deleted = True
        return self.update(instance)
