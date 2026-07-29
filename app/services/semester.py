from datetime import date
from math import ceil

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.exceptions.semester import (
    SemesterConflictError,
    SemesterNotFoundError,
    SemesterValidationError,
)
from app.models.semester import Semester, SemesterStatus
from app.repositories.semester import SemesterRepository
from app.schemas.semester import (
    SemesterCreate,
    SemesterUpdate,
)


class SemesterService:
    """
    Coordinate all Semester business rules.

    The service layer is responsible for:
    - Ownership enforcement.
    - Duplicate detection.
    - Date-range validation.
    - Partial update merging.
    - Repository coordination.
    - Transaction commit and rollback.

    HTTP-specific logic must remain outside this class.
    """

    def __init__(
        self,
        db: Session,
        repository: SemesterRepository | None = None,
    ) -> None:
        """
        Store the current database session and repository.

        repository is optional so unit tests can inject a mocked
        SemesterRepository instead of using a real database.
        """

        self.db = db
        self.repository = (
            repository
            if repository is not None
            else SemesterRepository(db)
        )

    def create_semester(
        self,
        user_id: int,
        semester_data: SemesterCreate,
    ) -> Semester:
        """
        Create a semester belonging to one user.

        Business rules:
        - start_date must be earlier than end_date.
        - The same user cannot have duplicate ACTIVE semesters with
          the same normalized name and academic year.
        - Another user may create an identical semester.
        """

        # Validate the date range again at service level.
        # Schema validation protects HTTP input, while service validation
        # protects the business rule regardless of where the service is called.
        self._validate_date_range(
            start_date=semester_data.start_date,
            end_date=semester_data.end_date,
        )

        # Duplicate restrictions only apply to ACTIVE semesters.
        if semester_data.status == SemesterStatus.ACTIVE:
            duplicate = self.repository.find_duplicate(
                user_id=user_id,
                name=semester_data.name,
                academic_year=semester_data.academic_year,
                status=SemesterStatus.ACTIVE,
            )

            if duplicate is not None:
                raise SemesterConflictError(
                    "An active semester with the same name and "
                    "academic year already exists."
                )

        # user_id comes from the authenticated user, not request data.
        semester = Semester(
            user_id=user_id,
            name=semester_data.name,
            academic_year=semester_data.academic_year,
            start_date=semester_data.start_date,
            end_date=semester_data.end_date,
            status=semester_data.status,
            description=semester_data.description,
        )

        try:
            # Repository adds, flushes and refreshes the ORM object.
            created_semester = self.repository.create(semester)

            # The service controls the transaction boundary.
            self.db.commit()

            return created_semester

        except IntegrityError as error:
            self.db.rollback()
            raise SemesterConflictError(
                "An active semester with the same name and "
                "academic year already exists."
            ) from error

        except SQLAlchemyError:
            # A failed flush or commit leaves the transaction unusable
            # until rollback is called.
            self.db.rollback()
            raise

    def get_semester(
        self,
        semester_id: int,
        user_id: int,
    ) -> Semester:
        """
        Return one semester belonging to the current user.

        A semester behaves as nonexistent when:
        - Its ID does not exist.
        - It belongs to another user.
        - It has been soft-deleted.

        The repository applies all three conditions in one query.
        """

        semester = self.repository.get_by_id_and_owner(
            semester_id=semester_id,
            user_id=user_id,
        )

        if semester is None:
            # Use one error for missing and inaccessible records.
            # This avoids revealing whether another user's semester exists.
            raise SemesterNotFoundError("Semester not found.")

        return semester

    def list_semesters(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: SemesterStatus | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict[str, object]:
        """
        List the current user's non-deleted semesters.

        Returns the records together with pagination information.

        The repository is responsible for:
        - Ownership filtering.
        - Soft-delete filtering.
        - Search.
        - Status filtering.
        - Sorting.
        - Offset and limit.
        """

        # Validate pagination before calculating the offset.
        if page < 1:
            raise SemesterValidationError(
                "Page must be greater than or equal to 1."
            )

        if page_size < 1:
            raise SemesterValidationError(
                "Page size must be greater than or equal to 1."
            )

        items = self.repository.list_by_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # count_by_user() must receive the same filters as list_by_user()
        # so the total matches the records displayed by the API.
        total = self.repository.count_by_user(
            user_id=user_id,
            search=search,
            status=status,
        )

        # For example, 41 records with page_size=20 require 3 pages.
        total_pages = ceil(total / page_size) if total > 0 else 0

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def update_semester(
        self,
        semester_id: int,
        user_id: int,
        semester_data: SemesterUpdate,
    ) -> Semester:
        """
        Partially update one semester belonging to the current user.

        Business rules:
        - Users cannot update another user's semester.
        - Deleted semesters behave as nonexistent.
        - Fields omitted from the request must remain unchanged.
        - The final merged date range must be valid.
        - Duplicate checks run when name or academic_year changes.
        - Duplicate checks also run when status changes to ACTIVE.
        """

        # get_semester() enforces ownership and excludes deleted records.
        semester = self.get_semester(
            semester_id=semester_id,
            user_id=user_id,
        )

        # exclude_unset=True includes only fields actually sent by the client.
        #
        # For example, if the request only sends:
        # {"description": "Updated"}
        #
        # update_data will not contain name, dates, status or academic_year.
        update_data = semester_data.model_dump(
            exclude_unset=True,
        )

        # An empty PATCH request does not change anything.
        if not update_data:
            return semester

        self._validate_required_update_values(update_data)

        # Merge new values with the current database values before validating.
        #
        # This is required because a partial update may contain only
        # start_date or only end_date.
        final_start_date = update_data.get(
            "start_date",
            semester.start_date,
        )

        final_end_date = update_data.get(
            "end_date",
            semester.end_date,
        )

        self._validate_date_range(
            start_date=final_start_date,
            end_date=final_end_date,
        )

        # Build the final identity fields after applying the partial update.
        final_name = update_data.get(
            "name",
            semester.name,
        )

        final_academic_year = update_data.get(
            "academic_year",
            semester.academic_year,
        )

        final_status = update_data.get(
            "status",
            semester.status,
        )

        # Compare normalized names so whitespace or letter casing does not
        # cause an unnecessary duplicate query.
        name_changed = (
            final_name.strip().lower()
            != semester.name.strip().lower()
        )

        academic_year_changed = (
            final_academic_year
            != semester.academic_year
        )

        status_changed_to_active = (
            semester.status != SemesterStatus.ACTIVE
            and final_status == SemesterStatus.ACTIVE
        )

        # The duplicate database constraint applies to ACTIVE semesters.
        #
        # Check when:
        # - name changes on an active semester;
        # - academic_year changes on an active semester; or
        # - an inactive semester becomes active.
        should_check_duplicate = (
            final_status == SemesterStatus.ACTIVE
            and (
                name_changed
                or academic_year_changed
                or status_changed_to_active
            )
        )

        if should_check_duplicate:
            duplicate = self.repository.find_duplicate(
                user_id=user_id,
                name=final_name,
                academic_year=final_academic_year,
                status=SemesterStatus.ACTIVE,
                exclude_semester_id=semester.id,
            )

            if duplicate is not None:
                raise SemesterConflictError(
                    "An active semester with the same name and "
                    "academic year already exists."
                )

        try:
            # Repository updates only the fields present in update_data.
            updated_semester = self.repository.update(
                semester=semester,
                update_data=update_data,
            )

            self.db.commit()

            return updated_semester

        except IntegrityError as error:
            self.db.rollback()
            raise SemesterConflictError(
                "An active semester with the same name and "
                "academic year already exists."
            ) from error

        except SQLAlchemyError:
            self.db.rollback()
            raise

    def delete_semester(
        self,
        semester_id: int,
        user_id: int,
    ) -> Semester:
        """
        Soft-delete one semester belonging to the current user.

        Users cannot delete another user's semester. A missing, inaccessible
        or previously deleted semester produces the same not-found result.
        """

        # Ownership and soft-delete checks happen before deletion.
        semester = self.get_semester(
            semester_id=semester_id,
            user_id=user_id,
        )

        try:
            deleted_semester = self.repository.soft_delete(
                semester
            )

            self.db.commit()

            return deleted_semester

        except SQLAlchemyError:
            self.db.rollback()
            raise

    @staticmethod
    def _validate_date_range(
        start_date: date,
        end_date: date,
    ) -> None:
        """
        Ensure the semester starts before it ends.

        This function is used by both creation and partial updates.
        """

        if start_date >= end_date:
            raise SemesterValidationError(
                "Semester start_date must be earlier than end_date."
            )

    @staticmethod
    def _validate_required_update_values(
        update_data: dict[str, object],
    ) -> None:
        """Reject explicit nulls for fields required by the domain model."""

        required_fields = {
            "name",
            "academic_year",
            "start_date",
            "end_date",
            "status",
        }
        null_fields = sorted(
            field
            for field in required_fields
            if field in update_data and update_data[field] is None
        )

        if null_fields:
            fields = ", ".join(null_fields)
            raise SemesterValidationError(
                f"Semester fields cannot be null: {fields}."
            )
