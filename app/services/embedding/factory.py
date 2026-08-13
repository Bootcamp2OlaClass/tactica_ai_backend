from app.core.config import Settings
from app.services.embedding.base import EmbeddingProvider
from app.services.embedding.exceptions import EmbeddingNotConfiguredError


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Lazy on purpose -- called only when embedding is actually attempted,
    not at app startup (same pattern as get_llm_provider)."""

    if settings.llm_provider == "gemini":
        from app.services.embedding.gemini_provider import GeminiEmbeddingProvider

        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
        )

    if settings.llm_provider == "openai":
        from app.services.embedding.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
        )

    raise EmbeddingNotConfiguredError(
        "No embedding provider is configured (set LLM_PROVIDER=gemini|openai "
        "plus the matching API key)."
    )
