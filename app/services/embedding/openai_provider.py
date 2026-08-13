"""OpenAI implementation of EmbeddingProvider — see ADR-007.

NOT VERIFIED against the real OpenAI API: no credentials were available in
this environment. Exercised only via a fake-provider test seam, same
honesty standard as app/services/llm/openai_provider.py.
"""

from openai import OpenAI

from app.services.embedding.base import EMBEDDING_DIMENSION, EmbeddingProvider
from app.services.embedding.exceptions import EmbeddingError, EmbeddingTransientError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, api_key: str, model: str, client=None) -> None:
        self.model = model
        self._client = client or OpenAI(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=texts,
                dimensions=EMBEDDING_DIMENSION,
            )
        except Exception as exc:
            raise EmbeddingTransientError(
                f"OpenAI embedding request failed: {exc}"
            ) from exc

        data = getattr(response, "data", None)
        if not data or len(data) != len(texts):
            raise EmbeddingError(
                "OpenAI returned an unexpected number of embeddings."
            )

        vectors: list[list[float]] = []
        for item in data:
            values = getattr(item, "embedding", None)
            if not values or len(values) != EMBEDDING_DIMENSION:
                raise EmbeddingError(
                    "OpenAI returned an embedding of unexpected dimension "
                    f"(expected {EMBEDDING_DIMENSION})."
                )
            vectors.append(list(values))

        return vectors
