from typing import ClassVar

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.common.exceptions import DatabaseError
from app.helper.base import BaseHelper


class HealthHelper(BaseHelper):
    """Readiness check: the service is up and the database answers."""

    STATUS_OK: ClassVar[str] = "ok"

    def check(self) -> dict[str, str]:
        try:
            self.db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            self.rollback()
            raise DatabaseError() from exc
        return {"status": self.STATUS_OK, "database": self.STATUS_OK}
