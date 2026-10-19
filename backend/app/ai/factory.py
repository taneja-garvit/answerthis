from app.ai.base import LLMProvider
from app.ai.providers.deterministic import DeterministicLLMProvider
from app.ai.providers.groq import GroqLLMProvider
from app.core.config import Settings


def build_llm_provider(settings: Settings) -> LLMProvider:
    """The only place that knows concrete providers. Settings validation has
    already guaranteed that a live provider has its key and model."""
    if settings.llm_provider == "groq":
        assert settings.groq_api_key is not None and settings.llm_model is not None
        return GroqLLMProvider(
            api_key=settings.groq_api_key,
            model=settings.llm_model,
            base_url=settings.groq_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            max_backoff_seconds=settings.llm_max_backoff_seconds,
        )
    return DeterministicLLMProvider()
