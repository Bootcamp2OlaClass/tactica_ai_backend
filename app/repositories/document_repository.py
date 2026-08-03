from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_active_by_course_and_checksum(
        self,
        course_id: int,
        checksum: str,
    ) -> Document | None:
        return (
            self.db.query(Document)
            .filter(
                Document.course_id == course_id,
                Document.checksum == checksum,
                Document.is_deleted.is_(False),
            )
            .first()
        )

    def create(
        self,
        document_data: dict,
    ) -> Document:
        document = Document(**document_data)

        self.db.add(document)
        self.db.flush()

        return document