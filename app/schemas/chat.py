"""Chat schemas — see PHASE_08_AI_STUDY_COACH.md.

`ChatCompletion` is the LLM's schema-enforced structured output (same
mechanism as Phase 06's `AcademicDocumentExtraction` / Phase 07's
embedding call, via `LLMProvider.extract_structured`) — the model
literally cannot emit free text outside this shape. `grounded` is the
model's own self-report of whether the answer actually relies on the
provided Tactica context (a document excerpt or the student's academic
data) to state a personal fact; `requires_personal_data` is the model's
separate self-report of whether the *question* needed the student's own
data at all, independent of whether it found any -- together they drive
ChatService's answer_mode (general / grounded / missing_personal_context).
`ChatCitation.chunk_id` values are re-verified against the chunks actually
retrieved this turn before being trusted (the ground-truth-filter step in
app/services/chat.py — never take the model's citation list at face
value).

The remaining classes are the public API response shapes.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.message import AnswerMode, MessageRole


class ChatCitation(BaseModel):
    chunk_id: int
    document_id: int


class ChatCompletion(BaseModel):
    answer: str
    grounded: bool
    requires_personal_data: bool = False
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = None
    course_id: int | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: MessageRole
    content: str
    grounded: bool | None
    citations: list[ChatCitation] | None
    answer_mode: AnswerMode | None
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class ChatResponse(BaseModel):
    conversation: ConversationResponse
    message: MessageResponse
