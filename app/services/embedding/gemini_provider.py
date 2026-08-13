"""Gemini implementation of EmbeddingProvider — see ADR-007.

NOT VERIFIED against the real Gemini API: no credentials were available in
this environment. Exercised only via a fake-provider test seam, same
honesty standard as app/services/llm/gemini_provider.py.
"""

from google import genai
from google.genai import types

from app.services.embedding.base import EMBEDDING_DIMENSION, EmbeddingProvider
from app.services.embedding.exceptions import EmbeddingError, EmbeddingTransientError


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, api_key: str, model: str, client=None) -> None:
        self.model = model
        self._client = client or genai.Client(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    output_dimensionality=EMBEDDING_DIMENSION
                ),
            )
        except Exception as exc:
            # Same broad-catch reasoning as the LLM providers: the SDK
            # doesn't expose one stable exception hierarchy across
            # transport vs. API-level failures.
            raise EmbeddingTransientError(
                f"Gemini embedding request failed: {exc}"
            ) from exc

        embeddings = getattr(response, "embeddings", None)
        if not embeddings or len(embeddings) != len(texts):
            raise EmbeddingError(
                "Gemini returned an unexpected number of embeddings."
            )

        vectors: list[list[float]] = []
        for item in embeddings:
            values = getattr(item, "values", None)
            if not values or len(values) != EMBEDDING_DIMENSION:
                raise EmbeddingError(
                    "Gemini returned an embedding of unexpected dimension "
                    f"(expected {EMBEDDING_DIMENSION})."
                )
            vectors.append(list(values))

        return vectors
