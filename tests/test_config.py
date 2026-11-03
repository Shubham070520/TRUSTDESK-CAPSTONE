import pytest

from app.config import Config, ErrorCode, ErrorConfig, SuccessConfig


class TestConfig:
    def test_load_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("TRUSTDESK_TOKEN", "TRUSTDESK_DB", "MODEL_PROVIDER", "MODEL_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        config = Config.load()
        assert config.model_provider == "mock"
        assert config.token == "demo-token"
        assert config.db_path.endswith("trustdesk.db")
        assert config.database_url.startswith("sqlite:///")

    def test_load_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MODEL_PROVIDER", "GROQ")
        monkeypatch.setenv("TRUSTDESK_TOKEN", "abc")
        config = Config.load()
        assert config.model_provider == "groq"
        assert config.token == "abc"

    def test_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValueError):
            Config(token="t", db_path="x.db", model_provider="openai")

    def test_table_prefix_default(self) -> None:
        assert Config.TABLE_PREFIX == "td_"


class TestErrorConfig:
    def test_every_code_has_message_and_status(self) -> None:
        for code in ErrorCode:
            assert ErrorConfig.message(code)
            assert 400 <= ErrorConfig.status(code) <= 599

    def test_codes_are_unique_1xxx(self) -> None:
        values = [int(c) for c in ErrorCode]
        assert len(values) == len(set(values))
        assert all(1000 <= v < 2000 for v in values)

    def test_http_status_mapping_falls_back_to_internal(self) -> None:
        assert ErrorConfig.code_for_http_status(404) == ErrorCode.NOT_FOUND
        assert ErrorConfig.code_for_http_status(418) == ErrorCode.INTERNAL


class TestSuccessConfig:
    def test_health_message_present(self) -> None:
        assert SuccessConfig.HEALTH_OK
