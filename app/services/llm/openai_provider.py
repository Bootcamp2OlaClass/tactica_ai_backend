"""OpenAI implementation of LLMProvider — see ADR-002.

NOT VERIFIED against the real OpenAI API: no credentials were available in
this environment. Exercised only indirectly, via DocumentExtractionService's
fake-provider test seam (tests/services/test_document_extraction.py) — this
class's own call to the real SDK is untested.
"""

from openai import OpenAI
from pydantic import ValidationError

from app.services.llm.base import LLMProvider, ResponseModel
from app.services.llm.exceptions import LLMExtractionError, LLMTransientError


class OpenAIProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, client=None) -> None:
        self.model = model
        self._client = client or OpenAI(api_key=api_key)

    def extract_structured(
        self,
        *,
        system_prompt: str,
        content: str,
        response_schema: type[ResponseModel],
    ) -> ResponseModel:
        try:
            completion = self._client.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                response_format=response_schema,
            )
        except Exception as exc:
            raise LLMTransientError(f"OpenAI request failed: {exc}") from exc

        choice = completion.choices[0] if completion.choices else None
        parsed = getattr(choice.message, "parsed", None) if choice else None

        if isinstance(parsed, response_schema):
            return parsed

        raw_content = choice.message.content if choice else None
        if not raw_content:
            raise LLMExtractionError(
                "OpenAI returned no parsable structured output."
            )

        try:
            return response_schema.model_validate_json(raw_content)
        except ValidationError as exc:
            raise LLMExtractionError(
                f"OpenAI output did not match the expected schema: {exc}"
            ) from exc
