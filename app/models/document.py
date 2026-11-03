from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Document(BaseModel):
    """A knowledge-base document. ``doc_id`` (e.g. KB-REFUND-001) is preserved exactly.

    The ingestion timestamp is the inherited ``updated_at``.
    The searchable section index lives in a separate FTS5 table.
    """

    doc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    source_path: Mapped[str] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(32))
    audience: Mapped[str] = mapped_column(String(200))
    checksum: Mapped[str] = mapped_column(String(64))
