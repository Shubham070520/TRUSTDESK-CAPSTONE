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
    FRONTEND_PAGE: ClassVar[Path] = BASE_DIR / "app" / "static" / "index.html"

    PROVIDER_MOCK: ClassVar[str] = "mock"
    PROVIDER_GEMINI: ClassVar[str] = "gemini"
    PROVIDER_GROQ: ClassVar[str] = "groq"
    PROVIDER_OPENROUTER: ClassVar[str] = "openrouter"
    VALID_PROVIDERS: ClassVar[tuple[str, ...]] = (
        PROVIDER_MOCK,
        PROVIDER_GEMINI,
        PROVIDER_GROQ,
        PROVIDER_OPENROUTER,
    )

    DEFAULT_PAGE: ClassVar[int] = 1
    DEFAULT_PAGE_SIZE: ClassVar[int] = 20
    MAX_PAGE_SIZE: ClassVar[int] = 100

    DEFAULT_SEARCH_K: ClassVar[int] = 5
    MAX_SEARCH_K: ClassVar[int] = 20
    MAX_QUERY_LENGTH: ClassVar[int] = 500
    # Documents retrieved for one draft, before unsafe ones are dropped.
    DRAFT_RETRIEVAL_K: ClassVar[int] = 5

    # Defaults for documents ingested through the API without these fields.
    DEFAULT_DOC_VERSION: ClassVar[str] = "unversioned"
    DEFAULT_DOC_AUDIENCE: ClassVar[str] = "unspecified"

    # Fixed identity behind the demo token (full role-based access is out of scope).
    REVIEWER_ID: ClassVar[str] = "demo-reviewer"

    # Model provider calls.
    MODEL_TIMEOUT_SECONDS: ClassVar[float] = 20.0
    # Largest goodwill coupon support may recommend (KB-COUPON-001). Larger needs a manager.
    MAX_STANDARD_COUPON_INR: ClassVar[int] = 1000

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
        model_name: str = "",
    ) -> None:
        provider = model_provider.strip().lower() or self.PROVIDER_MOCK
        if provider not in self.VALID_PROVIDERS:
            raise ValueError(
                f"MODEL_PROVIDER must be one of {self.VALID_PROVIDERS}, got {model_provider!r}"
            )
        if provider != self.PROVIDER_MOCK and not model_api_key.strip():
            raise ValueError(f"MODEL_API_KEY is required when MODEL_PROVIDER is {provider!r}")
        self._token = token
        self._db_path = db_path
        self._model_provider = provider
        self._model_api_key = model_api_key
        self._model_name = model_name.strip()

    @classmethod
    def load(cls) -> "Config":
        return cls(
            token=EnvReader.get("TRUSTDESK_TOKEN", "demo-token"),
            db_path=EnvReader.get("TRUSTDESK_DB", str(cls.BASE_DIR / "trustdesk.db")),
            model_provider=EnvReader.get("MODEL_PROVIDER", cls.PROVIDER_MOCK),
            model_api_key=EnvReader.get("MODEL_API_KEY", ""),
            model_name=EnvReader.get("MODEL_NAME", ""),
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
    def model_name(self) -> str:
        """Optional override of the provider's default model. Empty means use the default."""
        return self._model_name

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self._db_path}"
