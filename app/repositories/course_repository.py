from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.course import Course, CourseStatus
from app.models.semester import Semester


def create_course(
    db: Session,
    course_data: dict,
) -> Course:
    course = Course(**course_data)

    db.add(course)
    db.commit()
    db.refresh(course)

    return course


def get_course_by_id(
    db: Session,
    course_id: int,
    user_id: int,
) -> Course | None:
    return (
        db.query(Course)
        .join(Semester, Course.semester_id == Semester.id)
        .filter(
            Course.id == course_id,
            Semester.user_id == user_id,
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
        .first()
    )


def find_duplicate_course_code(
    db: Session,
    semester_id: int,
    course_code: str,
    user_id: int,
    exclude_course_id: int | None = None,
) -> Course | None:
    query = (
        db.query(Course)
        .join(Semester, Course.semester_id == Semester.id)
        .filter(
            Course.semester_id == semester_id,
            Course.course_code == course_code,
            Semester.user_id == user_id,
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
    )

    if exclude_course_id is not None:
        query = query.filter(
            Course.id != exclude_course_id
        )

    return query.first()


def list_courses_by_semester(
    db: Session,
    semester_id: int,
    user_id: int,
    offset: int = 0,
    limit: int = 20,
) -> list[Course]:
    return (
        db.query(Course)
        .join(Semester, Course.semester_id == Semester.id)
        .filter(
            Course.semester_id == semester_id,
            Semester.user_id == user_id,
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
        .order_by(Course.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def list_courses_by_user(
    db: Session,
    user_id: int,
    offset: int = 0,
    limit: int = 20,
    search: str | None = None,
    semester_id: int | None = None,
    status: CourseStatus | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list[Course]:
    query = (
        db.query(Course)
        .join(Semester, Course.semester_id == Semester.id)
        .filter(
            Semester.user_id == user_id,
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
    )

    if search:
        search_value = f"%{search.strip()}%"

        query = query.filter(
            or_(
                Course.course_code.ilike(search_value),
                Course.name.ilike(search_value),
            )
        )

    if semester_id is not None:
        query = query.filter(
            Course.semester_id == semester_id
        )

    if status is not None:
        query = query.filter(
            Course.status == status
        )

    allowed_sort_fields = {
        "course_code": Course.course_code,
        "name": Course.name,
        "status": Course.status,
        "created_at": Course.created_at,
        "updated_at": Course.updated_at,
    }

    sort_column = allowed_sort_fields.get(
        sort_by,
        Course.created_at,
    )

    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    return (
        query
        .offset(offset)
        .limit(limit)
        .all()
    )

def count_courses(
    db: Session,
    user_id: int,
    search: str | None = None,
    semester_id: int | None = None,
    status: CourseStatus | None = None,
) -> int:
    query = (
        db.query(Course)
        .join(Semester, Course.semester_id == Semester.id)
        .filter(
            Semester.user_id == user_id,
            Course.is_deleted.is_(False),
            Semester.is_deleted.is_(False),
        )
    )

    if search:
        search_value = f"%{search.strip()}%"

        query = query.filter(
            or_(
                Course.course_code.ilike(search_value),
                Course.name.ilike(search_value),
            )
        )

    if semester_id is not None:
        query = query.filter(
            Course.semester_id == semester_id
        )

    if status is not None:
        query = query.filter(
            Course.status == status
        )

    return query.count()

def update_course(
    db: Session,
    course: Course,
    update_data: dict,
) -> Course:
    allowed_fields = {
        "course_code",
        "name",
        "instructor_name",
        "credits",
        "classroom",
        "color",
        "description",
        "status",
    }

    for field, value in update_data.items():
        if field in allowed_fields:
            setattr(course, field, value)

    db.commit()
    db.refresh(course)

    return course

def soft_delete_course(
    db: Session,
    course: Course,
) -> Course:
    course.is_deleted = True
    course.deleted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(course)

    return course