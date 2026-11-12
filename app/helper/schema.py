from sqlalchemy import text

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.helper.base import BaseHelper
from app.models.base import Base, TableNames


class SchemaHelper(BaseHelper):
    """Creates the tables and the FTS5 search index. Safe to run repeatedly."""

    def init_schema(self) -> None:
        with self._guard():
            Base.metadata.create_all(bind=self.db.connection())
            self.db.execute(text(self._fts_ddl()))
            self.db.commit()

    @staticmethod
    def _fts_ddl() -> str:
        # One row per document section. Only doc_id is stored unindexed.
        return (
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {TableNames.documents_fts()} "
            "USING fts5(doc_id UNINDEXED, title, heading, body, "
            "tokenize='porter unicode61')"
        )
