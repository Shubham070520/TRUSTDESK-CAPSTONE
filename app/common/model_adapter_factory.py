from typing import ClassVar

from app.common.llm_adapter import (
    GeminiProtocol,
    GroqProtocol,
    LLMAdapter,
    OpenRouterProtocol,
    ProviderProtocol,
)
from app.common.mock_adapter import RuleBasedMockAdapter
from app.common.model_adapter import ModelAdapter
from app.config import Config


class ModelAdapterFactory:
    """Chooses the adapter named by ``MODEL_PROVIDER``."""

    _PROTOCOLS: ClassVar[dict[str, type[ProviderProtocol]]] = {
        Config.PROVIDER_GROQ: GroqProtocol,
        Config.PROVIDER_GEMINI: GeminiProtocol,
        Config.PROVIDER_OPENROUTER: OpenRouterProtocol,
    }

    def create(self, config: Config) -> ModelAdapter:
        if config.model_provider == Config.PROVIDER_MOCK:
            return RuleBasedMockAdapter()
        protocol = self._PROTOCOLS[config.model_provider]()
        return LLMAdapter(
            protocol=protocol,
            api_key=config.model_api_key,
            model=config.model_name,
        )
