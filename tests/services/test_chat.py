"""ChatService pipeline tests -- Retrieve -> Generate -> Validate ->
Ground-truth-filter -> Return (PHASE_08_AI_STUDY_COACH.md). Grounding
correctness (a hallucinated citation must never survive) and the
deterministic "I don't know" short-circuit are the two properties this
phase's acceptance criteria actually require; ownership isolation for
conversations is proven separately in tests/test_conversation_repository.py
and re-exercised here at the service level.
"""

from types import SimpleNamespace

import pytest

from app.exceptions.chat import ChatNotAvailableError, ConversationNotFoundError
from app.exceptions.rag import EmbeddingNotAvailableError
from app.models.document_chunk import DocumentChunk
from app.models.message import MessageRole
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatCitation, ChatCompletion
from app.services.chat import NO_CONTEXT_ANSWER, ChatService
from app.services.llm import LLMNotConfiguredError
from app.services.retrieval import RetrievalService
from tests.factories import create_document_with_owner, create_user_with_course


class FakeEmbeddingProvider:
    model = "fake-embedding-model"

    def __init__(self, vector=None):
        self._vector = vector or [0.5] * 768

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


class FakeLLMProvider:
    def __init__(self, completion: ChatCompletion | None = None):
        self._completion = completion
        self.calls: list[dict] = []

    def extract_structured(self, *, system_prompt, content, response_schema):
        self.calls.append({"system_prompt": system_prompt, "content": content})
        return self._completion


def _add_chunk(db_session, *, document, user_id, content, chunk_index=0):
    chunk = DocumentChunk(
        document_id=document.id,
        course_id=document.course_id,
        user_id=user_id,
        chunk_index=chunk_index,
        content=content,
        start_page=1,
        end_page=1,
        embedding=[0.5] * 768,
        embedding_model="fake/test-model",
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def _build_service(db_session, *, llm_completion=None, llm_provider=None):
    retrieval_service = RetrievalService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="gemini"),
        embedding_provider=FakeEmbeddingProvider(),
    )
    provider = llm_provider or FakeLLMProvider(llm_completion)
    service = ChatService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="gemini"),
        retrieval_service=retrieval_service,
        llm_provider=provider,
    )
    return service, provider


def test_send_message_short_circuits_for_a_completely_empty_account(db_session):
    from app.models.user import User, UserRole

    user = User(
        email=f"empty-{id(db_session)}@example.com",
        password_hash="hashed-password",
        full_name="Empty Account",
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    service, provider = _build_service(db_session, llm_completion=None)

    conversation, message = service.send_message(
        user_id=user.id, message="When is my exam?"
    )

    assert message.content == NO_CONTEXT_ANSWER
    assert message.grounded is False
    assert message.citations == []
    # The whole point of the short-circuit: no API call was made.
    assert provider.calls == []


def test_send_message_persists_user_and_assistant_turns(db_session):
    user, course = create_user_with_course(db_session, email_prefix="chat-persist")
    completion = ChatCompletion(
        answer="You have no exams on file.", grounded=True, citations=[]
    )
    service, _ = _build_service(db_session, llm_completion=completion)

    conversation, assistant_message = service.send_message(
        user_id=user.id, message="When is my exam?"
    )

    repository = ConversationRepository(db_session)
    messages = repository.list_messages(conversation_id=conversation.id)

    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[0].content == "When is my exam?"
    assert messages[1].role == MessageRole.ASSISTANT
    assert messages[1].content == "You have no exams on file."
    assert messages[1].id == assistant_message.id


def test_send_message_creates_a_new_conversation_with_a_derived_title(db_session):
    user, course = create_user_with_course(db_session, email_prefix="chat-new-conv")
    completion = ChatCompletion(answer="Sure.", grounded=True, citations=[])
    service, _ = _build_service(db_session, llm_completion=completion)

    conversation, _ = service.send_message(
        user_id=user.id, message="What's my course schedule?"
    )

    assert conversation.id is not None
    assert conversation.title == "What's my course schedule?"


def test_send_message_reuses_an_existing_conversation_and_includes_history(db_session):
    user, course = create_user_with_course(db_session, email_prefix="chat-history")
    completion = ChatCompletion(answer="Ok.", grounded=True, citations=[])
    service, provider = _build_service(db_session, llm_completion=completion)

    conversation, _ = service.send_message(user_id=user.id, message="First question")
    conversation_again, _ = service.send_message(
        user_id=user.id,
        message="Second question",
        conversation_id=conversation.id,
    )

    assert conversation_again.id == conversation.id
    # The second call's prompt content must include the first turn.
    second_call_content = provider.calls[-1]["content"]
    assert "First question" in second_call_content
    assert "Ok." in second_call_content


def test_send_message_raises_not_found_for_another_users_conversation(db_session):
    user_a, _ = create_user_with_course(db_session, email_prefix="chat-owner-a")
    user_b, _ = create_user_with_course(db_session, email_prefix="chat-owner-b")
    completion = ChatCompletion(answer="Ok.", grounded=True, citations=[])
    service, _ = _build_service(db_session, llm_completion=completion)

    conversation, _ = service.send_message(user_id=user_a.id, message="Hi")

    with pytest.raises(ConversationNotFoundError):
        service.send_message(
            user_id=user_b.id,
            message="Let me see A's conversation",
            conversation_id=conversation.id,
        )


def test_send_message_raises_when_no_llm_provider_is_configured(db_session, monkeypatch):
    user, course = create_user_with_course(db_session, email_prefix="chat-no-provider")
    retrieval_service = RetrievalService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="gemini"),
        embedding_provider=FakeEmbeddingProvider(),
    )
    service = ChatService(
        db=db_session,
        settings=SimpleNamespace(llm_provider=None),
        retrieval_service=retrieval_service,
        llm_provider=None,
    )

    def _raise_not_configured(settings):
        raise LLMNotConfiguredError("LLM_PROVIDER not set")

    monkeypatch.setattr("app.services.chat.get_llm_provider", _raise_not_configured)

    # There is a course on file (not a fully-empty account), so the
    # deterministic short-circuit does NOT apply -- the provider really
    # is reached and really does raise, which is what this test proves.
    with pytest.raises(ChatNotAvailableError):
        service.send_message(user_id=user.id, message="When is my exam?")


def test_send_message_degrades_gracefully_when_embeddings_are_unavailable(db_session):
    # Root-cause regression test for the "Couldn't send" bug: an unconfigured
    # (or transiently unreachable) embedding provider must not fail the
    # whole chat turn -- it should just mean no document chunks were
    # retrieved this turn, same graceful-degradation philosophy as
    # RecoveryPlanService's handling of a missing LLM provider.
    user, course = create_user_with_course(db_session, email_prefix="chat-no-embed")
    completion = ChatCompletion(
        answer="You're enrolled in one course.", grounded=True, citations=[]
    )

    class RaisingRetrievalService:
        def search(self, **kwargs):
            raise EmbeddingNotAvailableError("No embedding provider is configured.")

    provider = FakeLLMProvider(completion)
    service = ChatService(
        db=db_session,
        settings=SimpleNamespace(llm_provider="groq"),
        retrieval_service=RaisingRetrievalService(),
        llm_provider=provider,
    )

    _, message = service.send_message(user_id=user.id, message="What courses am I in?")

    assert message.content == "You're enrolled in one course."
    assert message.grounded is True
    # The LLM was still reached using academic context, proving this
    # degraded rather than short-circuiting to NO_CONTEXT_ANSWER.
    assert len(provider.calls) == 1


def test_send_message_keeps_a_citation_that_matches_a_retrieved_chunk(db_session):
    document, user = create_document_with_owner(db_session, email_prefix="chat-cite-ok")
    chunk = _add_chunk(
        db_session, document=document, user_id=user.id, content="The exam is Friday."
    )
    completion = ChatCompletion(
        answer="Your exam is Friday.",
        grounded=True,
        citations=[ChatCitation(chunk_id=chunk.id, document_id=document.id)],
    )
    service, _ = _build_service(db_session, llm_completion=completion)

    _, message = service.send_message(user_id=user.id, message="When is my exam?")

    assert message.grounded is True
    assert message.citations == [{"chunk_id": chunk.id, "document_id": document.id}]
    assert message.content == "Your exam is Friday."


def test_send_message_downgrades_a_fully_hallucinated_citation_to_not_grounded(
    db_session,
):
    document, user = create_document_with_owner(
        db_session, email_prefix="chat-cite-bad"
    )
    real_chunk = _add_chunk(
        db_session, document=document, user_id=user.id, content="The exam is Friday."
    )
    # The model cites a chunk_id that was never retrieved this turn (e.g.
    # invented, or a stale id from a previous turn) -- the ground-truth
    # filter must catch this even though the model claimed grounded=True.
    hallucinated_chunk_id = real_chunk.id + 999
    completion = ChatCompletion(
        answer="Your exam is Friday, per document X.",
        grounded=True,
        citations=[ChatCitation(chunk_id=hallucinated_chunk_id, document_id=document.id)],
    )
    service, _ = _build_service(db_session, llm_completion=completion)

    _, message = service.send_message(user_id=user.id, message="When is my exam?")

    assert message.grounded is False
    assert message.citations == []
    assert message.content == NO_CONTEXT_ANSWER


def test_send_message_passes_through_an_honest_ungrounded_answer(db_session):
    # Context exists (a course is on file) but doesn't answer this
    # specific question -- the model's own grounded=False must be
    # respected as-is, not treated as an error.
    user, course = create_user_with_course(db_session, email_prefix="chat-honest-idk")
    completion = ChatCompletion(
        answer="I don't have information about your degree requirements.",
        grounded=False,
        citations=[],
    )
    service, _ = _build_service(db_session, llm_completion=completion)

    _, message = service.send_message(
        user_id=user.id, message="What are my degree requirements?"
    )

    assert message.grounded is False
    assert message.content == "I don't have information about your degree requirements."
