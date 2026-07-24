from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.semester import Semester
    from app.models.task import Task
    from app.models.user import User

class Course(Base):
    __tablename__ = "courses"
    
    id: Mapped[int] = mapped_column(primary_key = True)
    
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable = False,
    )
    
    title: Mapped[str] = mapped_column(
       String(255),
       nullable = False,
    ) 
    
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id"),
        nullable=False,
    )
    
    professor: Mapped[str | None] = mapped_column(
        String(255),
        nullable = True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone= True),
        server_default = func.now(),
        nullable = False,
    )
    
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable = True,
        default = None,
    )
    
    #User.courses ↔ Course.user
    user: Mapped["User"] = relationship(
        back_populates = "courses"
    )
    
    # Course.tasks ↔ Task.course
    tasks: Mapped[list["Task"]] = relationship(
        back_populates = "course"
    )
    
    # Course.documents ↔ Document.course
    documents: Mapped[list["Document"]] = relationship(
        back_populates = "course"
    )
    
    semester: Mapped["Semester"] = relationship(
        back_populates="courses"
    )
