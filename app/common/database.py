from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Config


class Database:
    """Owns the engine and hands out sessions. Nothing else creates sessions."""

    def __init__(self, config: Config) -> None:
        self._engine: Engine = create_engine(
            config.database_url,
            connect_args={"check_same_thread": False},
        )
        event.listen(self._engine, "connect", self._configure_connection)
        self._session_factory = sessionmaker(
            bind=self._engine, autoflush=False, expire_on_commit=False
        )

    @staticmethod
    def _configure_connection(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """One session per unit of work, always closed afterwards."""
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def create_tables(self, metadata: Any) -> None:
        metadata.create_all(self._engine)

    def dispose(self) -> None:
        self._engine.dispose()
