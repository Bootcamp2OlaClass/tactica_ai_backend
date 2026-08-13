"""Repository-level tenant isolation tests -- the strongest, most direct
proof that DocumentChunkRepository.search can never surface another user's
chunks, exercised against a real Postgres + real pgvector column (no
mocks). See PHASE_07_RAG.md "Security" -- this is a phase completion
requirement, not optional polish.
"""

from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import DocumentChunkRepository
from tests.factories import create_document_with_owner


def _make_vector(seed: float) -> list[float]:
    return [seed] * 768


def _add_chunk(db_session, *, document, course_id, user_id, content, embedding, chunk_index=0):
    chunk = DocumentChunk(
        document_id=document.id,
        course_id=course_id,
        user_id=user_id,
        chunk_index=chunk_index,
        content=content,
        start_page=1,
        end_page=1,
        embedding=embedding,
        embedding_model="fake/test-model",
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return chunk


def test_search_never_returns_another_users_chunk_even_with_identical_embeddings(db_session):
    document_a, user_a = create_document_with_owner(db_session, email_prefix="user-a")
    document_b, user_b = create_document_with_owner(db_session, email_prefix="user-b")

    # Deliberately IDENTICAL embeddings -- pure vector similarity alone
    # would return both. Only the mandatory user_id filter can be relied
    # on to exclude user B's chunk from user A's search.
    identical_vector = _make_vector(0.5)
    chunk_a = _add_chunk(
        db_session,
        document=document_a,
        course_id=document_a.course_id,
        user_id=user_a.id,
        content="User A's private syllabus content.",
        embedding=identical_vector,
    )
    _add_chunk(
        db_session,
        document=document_b,
        course_id=document_b.course_id,
        user_id=user_b.id,
        content="User B's private syllabus content.",
        embedding=identical_vector,
    )

    repository = DocumentChunkRepository(db_session)

    results_for_a = repository.search(
        user_id=user_a.id, query_embedding=identical_vector, top_k=10
    )

    assert len(results_for_a) == 1
    assert results_for_a[0].id == chunk_a.id
    assert results_for_a[0].user_id == user_a.id


def test_search_isolation_holds_in_both_directions(db_session):
    document_a, user_a = create_document_with_owner(db_session, email_prefix="user-a")
    document_b, user_b = create_document_with_owner(db_session, email_prefix="user-b")

    identical_vector = _make_vector(0.5)
    _add_chunk(
        db_session,
        document=document_a,
        course_id=document_a.course_id,
        user_id=user_a.id,
        content="A's content.",
        embedding=identical_vector,
    )
    chunk_b = _add_chunk(
        db_session,
        document=document_b,
        course_id=document_b.course_id,
        user_id=user_b.id,
        content="B's content.",
        embedding=identical_vector,
    )

    repository = DocumentChunkRepository(db_session)

    results_for_b = repository.search(
        user_id=user_b.id, query_embedding=identical_vector, top_k=10
    )

    assert len(results_for_b) == 1
    assert results_for_b[0].id == chunk_b.id


def test_search_semantic_ranking_still_respects_isolation(db_session):
    # User B's chunk is embedded to be the *closest* possible match to the
    # query vector; user A's own chunk is farther away. If isolation were
    # implemented as an application-level post-filter over a top-k search
    # that didn't include the user_id predicate, user B's closer chunk
    # could crowd out or fully replace user A's results. It must not.
    document_a, user_a = create_document_with_owner(db_session, email_prefix="user-a")
    document_b, user_b = create_document_with_owner(db_session, email_prefix="user-b")

    query_vector = _make_vector(1.0)
    _add_chunk(
        db_session,
        document=document_a,
        course_id=document_a.course_id,
        user_id=user_a.id,
        content="A's somewhat-related content.",
        embedding=_make_vector(0.4),  # farther from query_vector
    )
    _add_chunk(
        db_session,
        document=document_b,
        course_id=document_b.course_id,
        user_id=user_b.id,
        content="B's near-perfect semantic match.",
        embedding=_make_vector(0.999),  # much closer to query_vector
    )

    repository = DocumentChunkRepository(db_session)

    results_for_a = repository.search(user_id=user_a.id, query_embedding=query_vector, top_k=10)

    assert len(results_for_a) == 1
    assert results_for_a[0].user_id == user_a.id
    assert results_for_a[0].content == "A's somewhat-related content."


def test_search_filters_by_course_id_within_the_same_user(db_session):
    document_1, user = create_document_with_owner(db_session, email_prefix="multi-course")
    # A second document/course pair, distinct from document_1's -- its
    # factory-generated owner is discarded, and its chunk is written with
    # `user.id` explicitly, to model "the same user has documents in two
    # different courses" without needing a second create-document helper.
    document_2, _ = create_document_with_owner(db_session, email_prefix="multi-course-2")

    vector = _make_vector(0.5)
    chunk_course_1 = _add_chunk(
        db_session,
        document=document_1,
        course_id=document_1.course_id,
        user_id=user.id,
        content="Course 1 content.",
        embedding=vector,
    )
    _add_chunk(
        db_session,
        document=document_2,
        course_id=document_2.course_id,
        user_id=user.id,
        content="Course 2 content.",
        embedding=vector,
    )

    repository = DocumentChunkRepository(db_session)

    results = repository.search(
        user_id=user.id,
        query_embedding=vector,
        course_id=document_1.course_id,
        top_k=10,
    )

    assert len(results) == 1
    assert results[0].id == chunk_course_1.id


def test_search_excludes_chunks_with_no_embedding_yet(db_session):
    document, user = create_document_with_owner(db_session, email_prefix="unembedded")

    _add_chunk(
        db_session,
        document=document,
        course_id=document.course_id,
        user_id=user.id,
        content="Embedded chunk.",
        embedding=_make_vector(0.5),
    )
    # A chunk row with no embedding yet shouldn't be constructible via
    # _add_chunk's signature requiring one -- insert directly instead.
    unembedded = DocumentChunk(
        document_id=document.id,
        course_id=document.course_id,
        user_id=user.id,
        chunk_index=1,
        content="Not yet embedded.",
        start_page=2,
        end_page=2,
        embedding=None,
        embedding_model=None,
    )
    db_session.add(unembedded)
    db_session.commit()

    repository = DocumentChunkRepository(db_session)
    results = repository.search(user_id=user.id, query_embedding=_make_vector(0.5), top_k=10)

    assert len(results) == 1
    assert results[0].content == "Embedded chunk."


def test_search_respects_top_k_limit(db_session):
    document, user = create_document_with_owner(db_session, email_prefix="many-chunks")

    for index in range(5):
        _add_chunk(
            db_session,
            document=document,
            course_id=document.course_id,
            user_id=user.id,
            content=f"Chunk {index}",
            embedding=_make_vector(0.1 * index),
            chunk_index=index,
        )

    repository = DocumentChunkRepository(db_session)
    results = repository.search(user_id=user.id, query_embedding=_make_vector(0.5), top_k=2)

    assert len(results) == 2


def test_search_returns_nothing_for_user_with_no_chunks(db_session):
    _, user_with_no_chunks = create_document_with_owner(db_session, email_prefix="lonely")

    repository = DocumentChunkRepository(db_session)
    results = repository.search(
        user_id=user_with_no_chunks.id, query_embedding=_make_vector(0.5), top_k=10
    )

    assert results == []
