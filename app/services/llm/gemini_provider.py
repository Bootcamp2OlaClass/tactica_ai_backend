"""Gemini implementation of LLMProvider — see ADR-002.

NOT VERIFIED against the real Gemini API: no credentials were available in
this environment. Contract-tested against a fake client (see
tests/services/llm/), same honesty standard as R2StorageProvider (ADR-004).
"""

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.services.llm.base import LLMProvider, ResponseModel
from app.services.llm.exceptions import LLMExtractionError, LLMTransientError


class GeminiProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, client=None) -> None:
        self.model = model
        self._client = client or genai.Client(api_key=api_key)

    def extract_structured(
        self,
        *,
        system_prompt: str,
        content: str,
        response_schema: type[ResponseModel],
    ) -> ResponseModel:
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
        except Exception as exc:
            # The SDK doesn't expose a single stable exception hierarchy
            # across transport failures (timeouts, connection errors) vs.
            # API-level errors (rate limits, 5xx) -- treat anything at the
            # call boundary as transient rather than silently swallowing a
            # real outage as "extraction failed."
            raise LLMTransientError(f"Gemini request failed: {exc}") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, response_schema):
            return parsed

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise LLMExtractionError(
                "Gemini returned no parsable structured output."
            )

        try:
            return response_schema.model_validate_json(raw_text)
        except ValidationError as exc:
            raise LLMExtractionError(
                f"Gemini output did not match the expected schema: {exc}"
            ) from exc
