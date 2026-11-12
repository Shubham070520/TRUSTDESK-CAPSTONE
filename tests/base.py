from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app import Application
from app.common.logger import Logger
from app.config import Config
from app.seed import SeedCommand


class ApiTestCase:
    """Shared fixtures. Test classes inherit from this."""

    TOKEN = "test-token"

    @pytest.fixture()
    def config(self, tmp_path: Path) -> Config:
        return Config(
            token=self.TOKEN,
            db_path=str(tmp_path / "test.db"),
            model_provider="mock",
        )

    @pytest.fixture()
    def application(self, config: Config) -> Iterator[Application]:
        application = Application(config)
        yield application
        application.database.dispose()

    @pytest.fixture()
    def client(self, application: Application) -> TestClient:
        return TestClient(application.create_app(), raise_server_exceptions=False)

    @pytest.fixture()
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.TOKEN}"}


class SeededApiTestCase(ApiTestCase):
    """Same as ``ApiTestCase`` but the database holds the real seed data."""

    @pytest.fixture()
    def application(self, config: Config) -> Iterator[Application]:
        SeedCommand(config, Logger("test-seed")).run()
        application = Application(config)
        yield application
        application.database.dispose()
