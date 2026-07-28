from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import Select

from app.models.semester import Semester, SemesterStatus


SEMESTER_SORT_FIELDS: dict[
    str,
    InstrumentedAttribute[Any],
] = {
    "id": Semester.id,
    "name": Semester.name,
    "academic_year": Semester.academic_year,
    "start_date": Semester.start_date,
    "end_date": Semester.end_date,
    "status": Semester.status,
    "created_at": Semester.created_at,
    "updated_at": Semester.updated_at,
}


SEMESTER_UPDATABLE_FIELDS: set[str] = {
    "name",
    "academic_year",
    "start_date",
    "end_date",
    "status",
    "description",
}


class SemesterRepository:
    """Handle all Semester persistence and database query logic."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        semester: Semester,
    ) -> Semester:
        """Add a new semester to the current database transaction."""

        self.db.add(semester)
        self.db.flush()
        self.db.refresh(semester)

        return semester

    def get_by_id_and_owner(
        self,
        semester_id: int,
        user_id: int,
    ) -> Semester | None:
        """
        Retrieve one non-deleted semester by ID and owner.

        Returning None allows the service layer to decide whether the
        situation should become a not-found or authorization error.
        """

        statement = select(Semester).where(
            Semester.id == semester_id,
            Semester.user_id == user_id,
            Semester.is_deleted.is_(False),
        )

        return self.db.scalar(statement)

    def find_duplicate(
        self,
        user_id: int,
        name: str,
        academic_year: int,
        exclude_semester_id: int | None = None,
    ) -> Semester | None:
        """
        Find a non-deleted semester with the same normalized name and
        academic year for one user.

        exclude_semester_id is used during updates so that the current
        semester is not considered a duplicate of itself.
        """

        normalized_name = name.strip()

        statement = select(Semester).where(
            Semester.user_id == user_id,
            func.lower(Semester.name)
            == normalized_name.lower(),
            Semester.academic_year == academic_year,
            Semester.is_deleted.is_(False),
        )

        if exclude_semester_id is not None:
            statement = statement.where(
                Semester.id != exclude_semester_id,
            )

        return self.db.scalar(statement)

    def list_by_user(
        self,
        user_id: int,
        page: int,
        page_size: int,
        search: str | None = None,
        status: SemesterStatus | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[Semester]:
        """
        List non-deleted semesters belonging to one user.

        The query supports search, status filtering, safe sorting and
        offset-based pagination.
        """

        statement = select(Semester)

        statement = self._apply_list_filters(
            statement=statement,
            user_id=user_id,
            search=search,
            status=status,
        )

        sort_column = self._get_sort_column(sort_by)
        normalized_sort_order = sort_order.strip().lower()

        if normalized_sort_order == "asc":
            statement = statement.order_by(
                sort_column.asc(),
                Semester.id.asc(),
            )
        elif normalized_sort_order == "desc":
            statement = statement.order_by(
                sort_column.desc(),
                Semester.id.desc(),
            )
        else:
            raise ValueError(
                f"Unsupported sort order: {sort_order}"
            )

        offset = (page - 1) * page_size

        statement = statement.offset(offset).limit(page_size)

        return list(self.db.scalars(statement).all())

    def count_by_user(
        self,
        user_id: int,
        search: str | None = None,
        status: SemesterStatus | None = None,
    ) -> int:
        """
        Count non-deleted semesters matching the same filters used by
        list_by_user().
        """

        statement = select(func.count(Semester.id)).where(
            Semester.user_id == user_id,
            Semester.is_deleted.is_(False),
        )

        normalized_search = self._normalize_search(search)

        if normalized_search is not None:
            statement = statement.where(
                Semester.name.ilike(
                    f"%{normalized_search}%"
                )
            )

        if status is not None:
            statement = statement.where(
                Semester.status == status,
            )

        total = self.db.scalar(statement)

        return total or 0

    def update(
        self,
        semester: Semester,
        update_data: dict[str, Any],
    ) -> Semester:
        """
        Apply approved updates to an existing Semester ORM object.

        The service layer should normally build update_data with
        schema.model_dump(exclude_unset=True).
        """

        unsupported_fields = (
            set(update_data) - SEMESTER_UPDATABLE_FIELDS
        )

        if unsupported_fields:
            fields = ", ".join(
                sorted(unsupported_fields)
            )
            raise ValueError(
                f"Unsupported semester update fields: {fields}"
            )

        for field_name, value in update_data.items():
            setattr(semester, field_name, value)

        self.db.add(semester)
        self.db.flush()
        self.db.refresh(semester)

        return semester

    def soft_delete(
        self,
        semester: Semester,
    ) -> Semester:
        """
        Mark a semester as deleted without removing its database row.
        """

        semester.is_deleted = True
        semester.deleted_at = datetime.now(timezone.utc)

        self.db.add(semester)
        self.db.flush()
        self.db.refresh(semester)

        return semester

    def _apply_list_filters(
        self,
        statement: Select[tuple[Semester]],
        user_id: int,
        search: str | None,
        status: SemesterStatus | None,
    ) -> Select[tuple[Semester]]:
        """
        Apply ownership, soft-delete, search and status conditions to
        a Semester list query.
        """

        statement = statement.where(
            Semester.user_id == user_id,
            Semester.is_deleted.is_(False),
        )

        normalized_search = self._normalize_search(search)

        if normalized_search is not None:
            statement = statement.where(
                Semester.name.ilike(
                    f"%{normalized_search}%"
                )
            )

        if status is not None:
            statement = statement.where(
                Semester.status == status,
            )

        return statement

    @staticmethod
    def _normalize_search(
        search: str | None,
    ) -> str | None:
        """
        Trim search input and treat an empty search value as no filter.
        """

        if search is None:
            return None

        normalized_search = search.strip()

        if not normalized_search:
            return None

        return normalized_search

    @staticmethod
    def _get_sort_column(
        sort_by: str,
    ) -> InstrumentedAttribute[Any]:
        """
        Return an approved SQLAlchemy column for sorting.

        Client input is never passed into raw SQL.
        """

        normalized_sort_by = sort_by.strip().lower()
        sort_column = SEMESTER_SORT_FIELDS.get(
            normalized_sort_by
        )

        if sort_column is None:
            raise ValueError(
                f"Unsupported sort field: {sort_by}"
            )

        return sort_column