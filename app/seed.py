"""Seed command: ``python -m app.seed``.

A command-line entry point (like ``run.py``), not part of the request flow.
It is the composition root for seeding: it builds the collaborators and injects them.
"""
from app.common.data_reader import DataFileReader
from app.common.database import Database
from app.common.document_parser import KnowledgeDocumentParser
from app.common.logger import Logger
from app.config import Config
from app.helper.document import DocumentHelper
from app.helper.schema import SchemaHelper
from app.helper.seed import SeedHelper


class SeedCommand:
    def __init__(self, config: Config, logger: Logger) -> None:
        self._config = config
        self._logger = logger

    def run(self) -> dict[str, int]:
        database = Database(self._config)
        try:
            with database.session_scope() as db:
                SchemaHelper(db).init_schema()
                seeder = SeedHelper(
                    db,
                    DataFileReader(Config.BASE_DIR, Config.DATA_DIR),
                    KnowledgeDocumentParser(),
                    DocumentHelper(db),
                )
                counts = seeder.seed_all()
        finally:
            database.dispose()
        for name, value in counts.items():
            self._logger.info(f"seeded {name}: {value}")
        return counts


if __name__ == "__main__":
    SeedCommand(Config.load(), Logger("seed")).run()
