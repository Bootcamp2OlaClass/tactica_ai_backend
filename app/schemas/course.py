from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.course import CourseStatus

COURSE_CODE_MAX_LENGTH = 50
COURSE_NAME_MAX_LENGTH = 255
COURSE_TEXT_MAX_LENGTH = 255
COURSE_DESCRIPTION_MAX_LENGTH = 2000


class CourseBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str = Field(min_length=1, max_length=COURSE_CODE_MAX_LENGTH)
    name: str = Field(min_length=1, max_length=COURSE_NAME_MAX_LENGTH)
    instructor_name: str | None = Field(default=None, max_length=COURSE_TEXT_MAX_LENGTH)
    credits: int = Field(ge=0, le=20)
    classroom: str | None = Field(default=None, max_length=COURSE_TEXT_MAX_LENGTH)
    color: str | None = Field(
        default=None,
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    description: str | None = Field(default=None, max_length=COURSE_DESCRIPTION_MAX_LENGTH)
    status: CourseStatus = CourseStatus.ACTIVE

    @field_validator("course_code", mode="before")
    @classmethod
    def normalize_course_code(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()

        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value


class CourseCreate(CourseBase):
    semester_id: int


class CourseCreateRequest(CourseBase):
    """Request body for creating a course under a semester path."""


class CourseUpdate(CourseBase):
    semester_id: int | None = None
    course_code: str | None = Field(default=None, min_length=1, max_length=COURSE_CODE_MAX_LENGTH)
    name: str | None = Field(default=None, min_length=1, max_length=COURSE_NAME_MAX_LENGTH)
    instructor_name: str | None = Field(default=None, max_length=COURSE_TEXT_MAX_LENGTH)
    credits: int | None = Field(default=None, ge=0, le=20)
    classroom: str | None = Field(default=None, max_length=COURSE_TEXT_MAX_LENGTH)
    color: str | None = Field(
        default=None,
        max_length=7,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )
    description: str | None = Field(default=None, max_length=COURSE_DESCRIPTION_MAX_LENGTH)
    status: CourseStatus | None = None


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    semester_id: int
    course_code: str
    name: str
    instructor_name: str | None
    credits: int
    classroom: str | None
    color: str | None
    description: str | None
    status: CourseStatus
    created_at: datetime
    updated_at: datetime


class CourseListResponse(BaseModel):
    items: list[CourseResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
