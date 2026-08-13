"""Ownership/isolation tests for ConversationRepository -- see
PHASE_08_AI_STUDY_COACH.md's security requirement: a conversation must
never leak another user's data. get_owned_by_id is the sole read path this
repository exposes for a single conversation, mirroring every other
owned-entity repository's discipline in this codebase.
"""

from app.models.message import MessageRole
from app.repositories.conversation_repository import ConversationRepository
from tests.factories import create_user_with_course


def test_get_owned_by_id_returns_none_for_another_users_conversation(db_session):
    user_a, _ = create_user_with_course(db_session, email_prefix="conv-a")
    user_b, _ = create_user_with_course(db_session, email_prefix="conv-b")

    repository = ConversationRepository(db_session)
    conversation = repository.create(user_id=user_a.id, title="A's conversation")
    db_session.commit()

    assert (
        repository.get_owned_by_id(conversation_id=conversation.id, user_id=user_b.id)
        is None
    )
    assert (
        repository.get_owned_by_id(conversation_id=conversation.id, user_id=user_a.id)
        is not None
    )


def test_list_by_user_never_includes_another_users_conversations(db_session):
    user_a, _ = create_user_with_course(db_session, email_prefix="conv-list-a")
    user_b, _ = create_user_with_course(db_session, email_prefix="conv-list-b")

    repository = ConversationRepository(db_session)
    repository.create(user_id=user_a.id, title="A's conversation")
    repository.create(user_id=user_b.id, title="B's conversation")
    db_session.commit()

    results = repository.list_by_user(user_id=user_a.id)

    assert len(results) == 1
    assert results[0].title == "A's conversation"


def test_add_message_and_list_messages_round_trip_in_order(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="conv-messages")
    repository = ConversationRepository(db_session)
    conversation = repository.create(user_id=user.id)
    db_session.commit()

    repository.add_message(
        conversation_id=conversation.id, role=MessageRole.USER, content="Question 1"
    )
    repository.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="Answer 1",
        grounded=True,
        citations=[{"chunk_id": 1, "document_id": 2}],
    )
    db_session.commit()

    messages = repository.list_messages(conversation_id=conversation.id)

    assert [m.role for m in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[0].content == "Question 1"
    assert messages[0].grounded is None
    assert messages[1].content == "Answer 1"
    assert messages[1].grounded is True
    assert messages[1].citations == [{"chunk_id": 1, "document_id": 2}]


def test_touch_bumps_updated_at(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="conv-touch")
    repository = ConversationRepository(db_session)
    conversation = repository.create(user_id=user.id)
    db_session.commit()
    original_updated_at = conversation.updated_at

    repository.add_message(
        conversation_id=conversation.id, role=MessageRole.USER, content="Hi"
    )
    repository.touch(conversation)
    db_session.commit()

    assert conversation.updated_at >= original_updated_at
