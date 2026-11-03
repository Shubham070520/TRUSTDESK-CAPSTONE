from contextlib import contextmanager
from typing import Iterator, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common.exceptions import DatabaseError, NotFoundError
from app.models.base import BaseModel

M = TypeVar("M", bound=BaseModel)


class BaseHelper:
    """Business logic and DB access. Knows nothing about HTTP.

    The session is injected, never created here.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    def db(self) -> Session:
        return self._db

    @contextmanager
    def _guard(self) -> Iterator[None]:
        """Roll back and raise ``DatabaseError`` if the wrapped DB work fails."""
        try:
            yield
        except SQLAlchemyError as exc:
            self.rollback()
            raise DatabaseError() from exc

    def commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self.rollback()
            raise DatabaseError() from exc

    def rollback(self) -> None:
        self._db.rollback()

    def get_by_uuid(self, model: type[M], uuid: str) -> M:
        """Return the live row with this public id or raise NotFoundError."""
        statement = select(model).where(model.uuid == uuid, model.is_deleted.is_(False))
        try:
            instance = self._db.execute(statement).scalar_one_or_none()
        except SQLAlchemyError as exc:
            self.rollback()
            raise DatabaseError() from exc
        if instance is None:
            raise NotFoundError()
        return instance

    def soft_delete(self, instance: BaseModel) -> None:
        instance.is_deleted = True
        self.commit()
