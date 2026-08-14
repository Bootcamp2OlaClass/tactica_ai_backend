"""Groq implementation of LLMProvider — see ADR-002.

Groq exposes an OpenAI-compatible REST API, so this reuses the already
-installed `openai` SDK pointed at Groq's base URL instead of adding a new
dependency. Groq's structured-output support (strict JSON-schema mode) is
inconsistent across models, so this does NOT use the OpenAI SDK's
`.chat.completions.parse()` convenience method (which assumes the server
honors strict `json_schema` response formatting). Instead it uses the more
widely-supported `response_format={"type": "json_object"}` ("JSON mode"),
embeds the target schema in the system prompt so the model knows the exact
shape to produce, and validates the result the same way OpenAIProvider's
manual-fallback branch already does.

Groq has no embeddings API — this provider only ever backs the LLM_PROVIDER
slot (chat generation, structured extraction), never the embedding provider
factory (see app/services/embedding/factory.py, which only supports
gemini/openai).
"""

import json

from openai import OpenAI
from pydantic import ValidationError

from app.services.llm.base import LLMProvider, ResponseModel
from app.services.llm.exceptions import LLMExtractionError, LLMTransientError

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, client=None) -> None:
        self.model = model
        self._client = client or OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    def extract_structured(
        self,
        *,
        system_prompt: str,
        content: str,
        response_schema: type[ResponseModel],
    ) -> ResponseModel:
        schema_instruction = (
            "\n\nRespond with a single JSON object only (no markdown, no "
            "commentary) that matches this JSON schema exactly:\n"
            f"{json.dumps(response_schema.model_json_schema())}"
        )

        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt + schema_instruction},
                    {"role": "user", "content": content},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise LLMTransientError(f"Groq request failed: {exc}") from exc

        choice = completion.choices[0] if completion.choices else None
        raw_content = choice.message.content if choice else None
        if not raw_content:
            raise LLMExtractionError("Groq returned no parsable structured output.")

        try:
            return response_schema.model_validate_json(raw_content)
        except ValidationError as exc:
            raise LLMExtractionError(
                f"Groq output did not match the expected schema: {exc}"
            ) from exc
