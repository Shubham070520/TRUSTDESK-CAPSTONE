import re
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.common.ids import UuidGenerator
from app.config import Config


class Base(DeclarativeBase):
    """Declarative root. Holds the shared metadata."""


class TableNames:
    """Single source of truth for prefixed table names and foreign-key targets."""

    @staticmethod
    def of(class_name: str) -> str:
        return f"{Config.TABLE_PREFIX}{class_name.lower()}"

    @classmethod
    def column(cls, class_name: str, column: str) -> str:
        """Foreign-key target string, e.g. ``td_customer.customer_id``."""
        return f"{cls.of(class_name)}.{column}"

    @classmethod
    def documents_fts(cls) -> str:
        """Name of the FTS5 table. Validated because it is placed in raw SQL."""
        name = f"{Config.TABLE_PREFIX}documents_fts"
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Unsafe table prefix: {Config.TABLE_PREFIX!r}")
        return name


class EnumColumn:
    """Builds a string-backed enum column type that stores enum *values*."""

    @staticmethod
    def _values(enum_cls: type[Enum]) -> list[str]:
        return [member.value for member in enum_cls]

    @classmethod
    def of(cls, enum_cls: type[Enum], length: int = 32) -> SqlEnum:
        return SqlEnum(
            enum_cls,
            native_enum=False,
            length=length,
            values_callable=cls._values,
            validate_strings=True,
        )


class BaseModel(Base):
    """Abstract parent of every table.

    ``id`` is internal. ``uuid`` is the public identifier. Rows are soft deleted.
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=UuidGenerator()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805 - SQLAlchemy declared_attr convention
        return TableNames.of(cls.__name__)

    def __repr__(self) -> str:
        attrs: dict[str, Any] = {"id": self.id, "uuid": self.uuid}
        inner = ", ".join(f"{k}={v!r}" for k, v in attrs.items())
        return f"{type(self).__name__}({inner})"
