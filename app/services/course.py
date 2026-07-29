from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions.course import (
    CourseConflictError,
    CourseNotFoundError,
    CourseValidationError,
)
from app.models.course import Course, CourseStatus
from app.repositories import course_repository
from app.repositories.semester import SemesterRepository
from app.schemas.course import CourseCreate, CourseUpdate


class CourseService:
    def __init__(
        self,
        db: Session,
        semester_repository: SemesterRepository | None = None,
    ) -> None:
        self.db = db
        self.semester_repository = (
            semester_repository
            if semester_repository is not None
            else SemesterRepository(db)
        )

    def _get_owned_semester(
        self,
        semester_id: int,
        user_id: int,
    ):
        semester = self.semester_repository.get_by_id_and_owner(
            semester_id=semester_id,
            user_id=user_id,
        )

        if semester is None:
            raise CourseNotFoundError("Semester not found.")

        return semester

    def create_course(
        self,
        user_id: int,
        course_data: CourseCreate,
    ) -> Course:
        self._get_owned_semester(
            semester_id=course_data.semester_id,
            user_id=user_id,
        )

        normalized_course_code = (
            course_data.course_code.strip().upper()
        )

        if course_data.status == CourseStatus.ACTIVE:
            duplicate = (
                course_repository.find_duplicate_course_code(
                    db=self.db,
                    semester_id=course_data.semester_id,
                    course_code=normalized_course_code,
                    user_id=user_id,
                )
            )

            if duplicate is not None:
                raise CourseConflictError(
                    "An active course with the same code already exists in this semester."
                )

        course_payload = {
            "semester_id": course_data.semester_id,
            "course_code": normalized_course_code,
            "name": course_data.name,
            "instructor_name": course_data.instructor_name,
            "credits": course_data.credits,
            "classroom": course_data.classroom,
            "color": course_data.color,
            "description": course_data.description,
            "status": course_data.status,
        }

        try:
            return course_repository.create_course(
                db=self.db,
                course_data=course_payload,
            )

        except IntegrityError as error:
            self.db.rollback()

            raise CourseConflictError(
                "An active course with the same code already exists in this semester."
            ) from error

        except SQLAlchemyError:
            self.db.rollback()
            raise

    def get_course(
        self,
        course_id: int,
        user_id: int,
    ) -> Course:
        course = course_repository.get_course_by_id(
            db=self.db,
            course_id=course_id,
            user_id=user_id,
        )

        if course is None:
            raise CourseNotFoundError("Course not found.")

        return course

    def list_courses(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        semester_id: int | None = None,
        status: CourseStatus | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, object]:
        if page < 1:
            raise CourseValidationError(
                "Page must be greater than or equal to 1."
            )

        if page_size < 1:
            raise CourseValidationError(
                "Page size must be greater than or equal to 1."
            )

        if semester_id is not None:
            self._get_owned_semester(
                semester_id=semester_id,
                user_id=user_id,
            )

        offset = (page - 1) * page_size

        items = course_repository.list_courses_by_user(
            db=self.db,
            user_id=user_id,
            offset=offset,
            limit=page_size,
            search=search,
            semester_id=semester_id,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total = course_repository.count_courses(
            db=self.db,
            user_id=user_id,
            search=search,
            semester_id=semester_id,
            status=status,
        )

        total_pages = (
            ceil(total / page_size)
            if total > 0
            else 0
        )

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }
    
    def update_course(
        self,
        course_id: int,
        user_id: int,
        course_data: CourseUpdate,
    ) -> Course:
        course = self.get_course(
            course_id=course_id,
            user_id=user_id,
        )

        update_data = course_data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            return course

        target_semester_id = update_data.get(
            "semester_id",
            course.semester_id,
        )

        if "semester_id" in update_data:
            self._get_owned_semester(
                semester_id=target_semester_id,
                user_id=user_id,
            )

        if "course_code" in update_data:
            normalized_course_code = (
                update_data["course_code"].strip().upper()
            )

            update_data["course_code"] = normalized_course_code

            target_status = update_data.get(
                "status",
                course.status,
            )

            if target_status == CourseStatus.ACTIVE:
                duplicate = (
                    course_repository.find_duplicate_course_code(
                        db=self.db,
                        semester_id=target_semester_id,
                        course_code=normalized_course_code,
                        user_id=user_id,
                        exclude_course_id=course_id,
                    )
                )

                if duplicate is not None:
                    raise CourseConflictError(
                        "An active course with the same code already exists in this semester."
                    )

        elif (
            "semester_id" in update_data
            or update_data.get("status") == CourseStatus.ACTIVE
        ):
            target_status = update_data.get(
                "status",
                course.status,
            )

            if target_status == CourseStatus.ACTIVE:
                duplicate = (
                    course_repository.find_duplicate_course_code(
                        db=self.db,
                        semester_id=target_semester_id,
                        course_code=course.course_code,
                        user_id=user_id,
                        exclude_course_id=course_id,
                    )
                )

                if duplicate is not None:
                    raise CourseConflictError(
                        "An active course with the same code already exists in this semester."
                    )

        try:
            return course_repository.update_course(
                db=self.db,
                course=course,
                update_data=update_data,
            )

        except IntegrityError as error:
            self.db.rollback()

            raise CourseConflictError(
                "An active course with the same code already exists in this semester."
            ) from error

        except SQLAlchemyError:
            self.db.rollback()
            raise

    
    def delete_course(
        self,
        course_id: int,
        user_id: int,
    ) -> Course:
        course = self.get_course(
            course_id=course_id,
            user_id=user_id,
        )

        try:
            return course_repository.soft_delete_course(
                db=self.db,
                course=course,
            )

        except SQLAlchemyError:
            self.db.rollback()
            raise
        