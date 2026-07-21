from enum import Enum
from datetime import datetime


from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.db.base import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.course import Course

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Document(Base):
    __tablename__ = "documents"
    
    id: Mapped[int] = mapped_column(
        primary_key = True
    )
    
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable = False
    )
    
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable = False,
    )
    
    file_path: Mapped[str] = mapped_column(
        String(255),
        nullable = False,
    )
    
    status: Mapped[DocumentStatus] = mapped_column(
        SQLEnum(DocumentStatus),
        nullable = False,
        default = DocumentStatus.PENDING,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone = True),
        server_default = func.now(),
        nullable = False,
    )
    
    deleted_at: Mapped[datetime|None] = mapped_column(
        DateTime(timezone=True),
        nullable = True,
        default = None,
    )
    
    course: Mapped["Course"] = relationship(
        back_populates = "documents"
    )