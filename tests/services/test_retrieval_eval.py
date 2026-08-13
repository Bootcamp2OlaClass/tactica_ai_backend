"""Retrieval evaluation suite — the fixed question/expected-chunk pairs
required by PHASE_07_RAG.md's task checklist and acceptance criteria.

This is a different concern from test_retrieval.py and
tests/test_document_chunk_repository.py (which prove tenant isolation and
plumbing correctness with deliberately-identical or hand-picked vectors).
This suite proves the *ranking* itself is sound: given a realistic mix of
topically-distinct chunks for one user, does a question about topic X
actually retrieve the chunk about topic X ahead of same-user distractors
about topics Y/Z?

No real embedding credentials exist in this environment (see ADR-007 /
app/services/embedding/gemini_provider.py's own NOT VERIFIED note), so this
suite uses a deterministic, keyword-grounded fake embedding provider
instead of a real model. It is deliberately NOT a trivial fake (unlike
FakeEmbeddingProvider in test_retrieval.py, which always returns one fixed
vector) -- it encodes real topical structure into cosine space, so a
regression in DocumentChunkRepository.search's ORDER BY / distance
operator, or in RetrievalService's wiring, would show up as a wrong-topic
result here even though it would NOT show up in the identical-vector
isolation tests.

Accuracy bar: 100% top-1 topic accuracy across the fixed set below. Since
the embedding signal is deterministic and unambiguous by construction, a
correct implementation has no excuse to miss any of them -- this bar
should be revisited (see PHASE_07_RAG.md "Acceptance Criteria") once real
Gemini/OpenAI embeddings are evaluated against real syllabus text, where
100% would not be a realistic target.
"""

from app.models.document_chunk import DocumentChunk
from app.services.retrieval import RetrievalService
from tests.factories import create_document_with_owner

EMBEDDING_DIMENSION = 768

# Each topic owns one dedicated dimension -- keyword hits add signal only
# to that dimension, so cosine similarity directly reflects topical
# overlap between a query and a chunk, exactly like a real embedding space
# separates unrelated concepts.
TOPIC_DIMENSIONS = {
    "exam_schedule": 0,
    "office_hours": 1,
    "grading_policy": 2,
    "required_textbook": 3,
    "attendance_policy": 4,
    "late_submission": 5,
    "prerequisites": 6,
    "instructor_contact": 7,
}

TOPIC_KEYWORDS = {
    "exam_schedule": ["exam", "midterm", "test date"],
    "office_hours": ["office hours", "drop-in", "student hours"],
    "grading_policy": ["grading", "grade", "weighted average", "rubric"],
    "required_textbook": ["textbook", "required reading", "isbn", "course text", "book"],
    "attendance_policy": ["attendance", "absence", "show up", "missed class"],
    "late_submission": ["late submission", "late penalty", "deadline extension", "late"],
    "prerequisites": ["prerequisite", "prior coursework", "required background", "before this"],
    "instructor_contact": ["professor email", "instructor contact", "reach the professor", "email"],
}


class FakeTopicEmbeddingProvider:
    """Deterministic stand-in for a real embedding model: one-hot(ish) over
    TOPIC_DIMENSIONS by keyword match, so unrelated topics are orthogonal
    (cosine similarity 0) and matching topics are maximally similar --
    real embedding spaces approximate this for genuinely distinct
    concepts, which is exactly the property this suite needs to exercise
    ranking correctly."""

    model = "fake-topic-embedding-eval"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        lowered = text.lower()
        vector = [0.0] * EMBEDDING_DIMENSION
        matched = False
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                vector[TOPIC_DIMENSIONS[topic]] = 1.0
                matched = True
        if not matched:
            # A small, fixed baseline signal outside every topic dimension
            # -- keeps the vector non-zero (cosine distance is undefined
            # for a true zero vector) without ever aliasing a real topic.
            vector[-1] = 0.01
        return vector


# The fixed evaluation set. Each chunk is realistic syllabus-style prose;
# each question is phrased the way a student actually would, not just a
# keyword echo of the chunk (e.g. "When do I need to show up on time?"
# maps to attendance_policy without repeating "attendance").
EVAL_CHUNKS = [
    ("exam_schedule", "The midterm exam will be held in week 8. The last exam of the term covers all material from the semester."),
    ("office_hours", "Office hours are Tuesdays and Thursdays from 2-4pm in room 214, drop-in, no appointment needed -- these are your dedicated student hours."),
    ("grading_policy", "Final grades are calculated as a weighted average of assignments and coursework. See the grading rubric distributed in week 1 for the exact breakdown."),
    ("required_textbook", "The required textbook for this course is 'Algorithms Illustrated', ISBN 978-0-13-468599-1. This course text/book is available at the campus bookstore."),
    ("attendance_policy", "Attendance is mandatory. If you cannot show up, notify the instructor in advance -- unexcused absences will affect your participation score."),
    ("late_submission", "Late submission of assignments incurs a 10% per-day penalty. Deadline extension requests require documented medical or emergency circumstances."),
    ("prerequisites", "This course assumes prior coursework in discrete mathematics and basic programming. This prerequisite is required background before this course begins."),
    ("instructor_contact", "You can reach the professor at instructor@university.edu -- sending a professor email is the fastest way to get instructor contact outside class."),
]

EVAL_QUESTIONS = [
    ("When is the midterm exam?", "exam_schedule"),
    ("What time are the professor's office hours?", "office_hours"),
    ("How is my final grade calculated?", "grading_policy"),
    ("What book do I need to buy for this class?", "required_textbook"),
    ("Do I need to show up to every class?", "attendance_policy"),
    ("What happens if I turn in my assignment late?", "late_submission"),
    ("Do I need to have taken another course before this one?", "prerequisites"),
    ("How do I email the instructor?", "instructor_contact"),
]


def _seed_eval_chunks(db_session) -> tuple[dict[str, DocumentChunk], object]:
    document, user = create_document_with_owner(db_session, email_prefix="eval-set")
    provider = FakeTopicEmbeddingProvider()

    chunks_by_topic: dict[str, DocumentChunk] = {}
    for index, (topic, content) in enumerate(EVAL_CHUNKS):
        chunk = DocumentChunk(
            document_id=document.id,
            course_id=document.course_id,
            user_id=user.id,
            chunk_index=index,
            content=content,
            start_page=1,
            end_page=1,
            embedding=provider.embed([content])[0],
            embedding_model=provider.model,
        )
        db_session.add(chunk)
        chunks_by_topic[topic] = chunk

    db_session.commit()
    return chunks_by_topic, user


def test_retrieval_eval_set_meets_the_100_percent_top1_accuracy_bar(db_session):
    """The mandatory fixed eval set. See module docstring for the accuracy
    bar and why 100% is the right target for this deterministic fixture
    (as opposed to a real-model evaluation, which is a separate, not-yet-
    runnable concern tracked as NOT VERIFIED)."""

    chunks_by_topic, user = _seed_eval_chunks(db_session)
    assert len(chunks_by_topic) == len(TOPIC_KEYWORDS), (
        "eval fixture is missing a topic -- fix the fixture before trusting the score"
    )

    provider = FakeTopicEmbeddingProvider()
    service = RetrievalService(
        db=db_session,
        settings=None,
        embedding_provider=provider,
    )

    failures = []
    for question, expected_topic in EVAL_QUESTIONS:
        results = service.search(user_id=user.id, query=question, top_k=1)
        expected_chunk = chunks_by_topic[expected_topic]

        if not results or results[0].chunk_id != expected_chunk.id:
            actual = results[0].content if results else "<no results>"
            failures.append(
                f"Q: {question!r} expected topic {expected_topic!r} "
                f"({expected_chunk.content!r}) but got {actual!r}"
            )

    accuracy = (len(EVAL_QUESTIONS) - len(failures)) / len(EVAL_QUESTIONS)
    assert not failures, (
        f"retrieval eval accuracy {accuracy:.0%} (bar: 100%), failures:\n"
        + "\n".join(failures)
    )


def test_retrieval_eval_set_top1_beats_same_user_distractors_individually():
    """Sanity check on the fixture itself, independent of the DB/service:
    every eval chunk's embedding must be strictly more similar to its own
    question than to any other topic's chunk -- otherwise the 100% bar
    above would be meaningless (satisfiable only by accident of tie-
    breaking). Pure vector-math check, no database needed."""

    provider = FakeTopicEmbeddingProvider()
    chunk_vectors = {
        topic: provider.embed([content])[0] for topic, content in EVAL_CHUNKS
    }

    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b)

    for question, expected_topic in EVAL_QUESTIONS:
        query_vector = provider.embed([question])[0]
        expected_similarity = cosine_similarity(query_vector, chunk_vectors[expected_topic])

        for other_topic, other_vector in chunk_vectors.items():
            if other_topic == expected_topic:
                continue
            other_similarity = cosine_similarity(query_vector, other_vector)
            assert expected_similarity > other_similarity, (
                f"fixture is ambiguous: {question!r} is not more similar to "
                f"{expected_topic!r} than to distractor {other_topic!r}"
            )
