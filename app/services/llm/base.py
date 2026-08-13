"""Provider-agnostic LLM abstraction — see ADR-002.

Every real provider (Gemini, OpenAI) enforces the output shape via the
provider API's own structured-output mode (JSON-schema-constrained
generation), not by asking nicely in a prompt and hoping. This is also the
primary mitigation for document-based prompt injection (Phase 06 scope
note): the model literally cannot emit anything outside the schema,
regardless of what instructions an untrusted document's text might try to
inject.
"""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    def extract_structured(
        self,
        *,
        system_prompt: str,
        content: str,
        response_schema: type[ResponseModel],
    ) -> ResponseModel:
        """Call the model with `content` as untrusted user-role input (never
        concatenated into the system prompt) and return an instance of
        `response_schema`, enforced by the provider's own structured-output
        mode. Raises LLMExtractionError if the provider ultimately can't
        produce schema-valid output."""
