from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk


class DocumentChunkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def delete_by_document(self, document_id: int) -> None:
        """Used before a (re-)embed pass -- unlike Phase 06's candidates,
        chunks have no review/accept state to preserve, so a re-run simply
        replaces all of a document's chunks outright."""
        (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .delete()
        )
        self.db.flush()

    def bulk_create(self, chunks: list[dict]) -> list[DocumentChunk]:
        objects = [DocumentChunk(**chunk) for chunk in chunks]
        self.db.add_all(objects)
        self.db.flush()
        return objects

    def list_by_document(self, document_id: int) -> list[DocumentChunk]:
        return (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

    def search(
        self,
        *,
        user_id: int,
        query_embedding: list[float],
        course_id: int | None = None,
        top_k: int = 5,
    ) -> list[DocumentChunk]:
        """The tenant-isolation-critical query -- `user_id` is a mandatory
        keyword-only argument (not optional), and the filter is applied
        directly in SQL, never as an application-level post-filter over a
        broader search. See tests/services/test_retrieval.py for the
        explicit cross-user isolation proof this method must satisfy."""
        query = self.db.query(DocumentChunk).filter(
            DocumentChunk.user_id == user_id,
            DocumentChunk.embedding.is_not(None),
        )

        if course_id is not None:
            query = query.filter(DocumentChunk.course_id == course_id)

        return (
            query.order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
            .limit(top_k)
            .all()
        )
