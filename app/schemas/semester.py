from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel, 
    ConfigDict, 
    Field, 
    field_validator, 
    model_validator)

from app.models.semester import SemesterStatus

SEMESTER_NAME_MAX_LENGTH = 255
SEMESTER_DESCRIPTION_MAX_LENGTH = 255

class SemesterBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=SEMESTER_NAME_MAX_LENGTH,
    )
    academic_year: int = Field(
        ge=2000,
        le=2100,
    )
    start_date: date
    end_date: date
    status: SemesterStatus = SemesterStatus.UPCOMING
    description: str | None = Field(
        default=None,
        max_length=SEMESTER_DESCRIPTION_MAX_LENGTH,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date >= self.end_date:
            raise ValueError(
                "Start date must be earlier than end date."
            )

        return self

class SemesterCreate(SemesterBase):
    pass


class SemesterUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=SEMESTER_NAME_MAX_LENGTH,
    )
    academic_year: int | None = Field(
        default=None,
        ge=2000,
        le=2100,
    )
    start_date: date | None = None
    end_date: date | None = None
    status: SemesterStatus | None = None
    description: str | None = Field(
        default=None,
        max_length=SEMESTER_DESCRIPTION_MAX_LENGTH,
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date >= self.end_date
        ):
            raise ValueError(
                "Start date must be earlier than end date."
            )

        return self


class SemesterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    academic_year: int
    start_date: date
    end_date: date
    status: SemesterStatus
    description: str | None
    created_at: datetime
    updated_at: datetime


class SemesterListResponse(BaseModel):
    items: list[SemesterResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)