"""Application settings. Values come from the environment, never from source."""
import os
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv


class EnvReader:
    """Reads environment variables, loading a local .env file once."""

    _ENV_FILE: ClassVar[Path] = Path(__file__).resolve().parent.parent.parent / ".env"
    _loaded: ClassVar[bool] = False

    @classmethod
    def _ensure_loaded(cls) -> None:
        if not cls._loaded:
            load_dotenv(cls._ENV_FILE)
            cls._loaded = True

    @classmethod
    def get(cls, name: str, default: str) -> str:
        cls._ensure_loaded()
        return os.getenv(name, default)


class Config:
    """Immutable settings object. Build it with ``Config.load()`` or pass values."""

    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: ClassVar[Path] = BASE_DIR / "data"

    PROVIDER_MOCK: ClassVar[str] = "mock"
    PROVIDER_GEMINI: ClassVar[str] = "gemini"
    PROVIDER_GROQ: ClassVar[str] = "groq"
    VALID_PROVIDERS: ClassVar[tuple[str, ...]] = (
        PROVIDER_MOCK,
        PROVIDER_GEMINI,
        PROVIDER_GROQ,
    )

    DEFAULT_PAGE: ClassVar[int] = 1
    DEFAULT_PAGE_SIZE: ClassVar[int] = 20
    MAX_PAGE_SIZE: ClassVar[int] = 100

    DEFAULT_SEARCH_K: ClassVar[int] = 5
    MAX_SEARCH_K: ClassVar[int] = 20
    MAX_QUERY_LENGTH: ClassVar[int] = 500

    # Defaults for documents ingested through the API without these fields.
    DEFAULT_DOC_VERSION: ClassVar[str] = "unversioned"
    DEFAULT_DOC_AUDIENCE: ClassVar[str] = "unspecified"

    # Fixed identity behind the demo token (full role-based access is out of scope).
    REVIEWER_ID: ClassVar[str] = "demo-reviewer"

    DEFAULT_HOST: ClassVar[str] = "127.0.0.1"
    DEFAULT_PORT: ClassVar[int] = 8000

    # Read at import time because model table names are fixed when classes are defined.
    TABLE_PREFIX: ClassVar[str] = EnvReader.get("TRUSTDESK_TABLE_PREFIX", "td_")

    def __init__(
        self,
        token: str,
        db_path: str,
        model_provider: str,
        model_api_key: str = "",
    ) -> None:
        provider = model_provider.strip().lower() or self.PROVIDER_MOCK
        if provider not in self.VALID_PROVIDERS:
            raise ValueError(
                f"MODEL_PROVIDER must be one of {self.VALID_PROVIDERS}, got {model_provider!r}"
            )
        self._token = token
        self._db_path = db_path
        self._model_provider = provider
        self._model_api_key = model_api_key

    @classmethod
    def load(cls) -> "Config":
        return cls(
            token=EnvReader.get("TRUSTDESK_TOKEN", "demo-token"),
            db_path=EnvReader.get("TRUSTDESK_DB", str(cls.BASE_DIR / "trustdesk.db")),
            model_provider=EnvReader.get("MODEL_PROVIDER", cls.PROVIDER_MOCK),
            model_api_key=EnvReader.get("MODEL_API_KEY", ""),
        )

    @property
    def token(self) -> str:
        return self._token

    @property
    def db_path(self) -> str:
        return self._db_path

    @property
    def model_provider(self) -> str:
        return self._model_provider

    @property
    def model_api_key(self) -> str:
        return self._model_api_key

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self._db_path}"
