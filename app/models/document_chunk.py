from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.services.embedding.base import EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.document import Document
    from app.models.user import User


class DocumentChunk(Base):
    """One retrievable, embedded slice of a document's Phase 05 normalized
    text — see PHASE_07_RAG.md and ADR-003/007/008.

    `user_id`/`course_id` are deliberately denormalized from
    document->course->semester rather than requiring a join at retrieval
    time: tenant isolation is this table's core security property, and a
    direct `WHERE user_id = :user_id` on this table is the most auditable
    way to guarantee it (see ADR-003's tenant-isolation reasoning).
    """

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    start_page: Mapped[int] = mapped_column(Integer, nullable=False)

    end_page: Mapped[int] = mapped_column(Integer, nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
        default=None,
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    course: Mapped["Course"] = relationship()

    user: Mapped["User"] = relationship()
