"""Provider-agnostic embedding abstraction — see ADR-007.

Mirrors app/services/llm/base.py's shape deliberately: same provider
selection (Gemini default / OpenAI alternate, via LLM_PROVIDER — see
ADR-007's "one vendor governs both" rationale), same lazy-construction
pattern, same NOT VERIFIED-until-real-credentials honesty standard.
"""

from abc import ABC, abstractmethod

EMBEDDING_DIMENSION = 768  # fixed by ADR-007 — both providers requested at this size


class EmbeddingProvider(ABC):
    # Every implementation sets this in __init__ (the exact model name
    # requested, e.g. "gemini-embedding-001") -- used for chunk
    # provenance labeling (DocumentChunk.embedding_model), not enforced by
    # the type system since it's a plain instance attribute, not a method.
    model: str

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one EMBEDDING_DIMENSION-length vector per input text, in
        the same order. Raises EmbeddingTransientError for a retryable
        provider-side failure, EmbeddingError for a permanent one."""
