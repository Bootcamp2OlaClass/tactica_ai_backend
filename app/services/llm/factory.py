from app.core.config import Settings
from app.services.llm.base import LLMProvider
from app.services.llm.exceptions import LLMNotConfiguredError


def get_llm_provider(settings: Settings) -> LLMProvider:
    """Lazy on purpose -- called only when extraction is actually
    attempted, not at app startup, so the app boots fine with zero LLM
    configuration (same pattern as Redis/R2)."""

    if settings.llm_provider == "gemini":
        from app.services.llm.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    if settings.llm_provider == "openai":
        from app.services.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    raise LLMNotConfiguredError(
        "No LLM provider is configured (set LLM_PROVIDER=gemini|openai "
        "plus the matching API key)."
    )
