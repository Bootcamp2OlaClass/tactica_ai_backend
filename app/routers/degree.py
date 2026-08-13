from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.exceptions.degree import DegreeProgramNotFoundError
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.degree import (
    DeclareDegreeProgramRequest,
    DegreeProgressResponse,
    EligibleCourseResponse,
)
from app.services.degree_recommendation import (
    DegreeProgressService,
    DegreeRecommendationService,
    NoDeclaredDegreeProgramError,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["Degree Advisor"],
)

DEGREE_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "No degree program declared, or the referenced program doesn't exist",
    },
}


def get_degree_progress_service(db: Session = Depends(get_db)) -> DegreeProgressService:
    return DegreeProgressService(db)


def get_degree_recommendation_service(
    db: Session = Depends(get_db),
) -> DegreeRecommendationService:
    return DegreeRecommendationService(db, get_settings())


def raise_degree_http_exception(error: Exception) -> NoReturn:
    if isinstance(error, (NoDeclaredDegreeProgramError, DegreeProgramNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)) from error


@router.post(
    "/degree-progress/declare",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=DEGREE_ERROR_RESPONSES,
)
def declare_degree_program(
    body: DeclareDegreeProgramRequest,
    current_user: User = Depends(get_current_user),
    service: DegreeProgressService = Depends(get_degree_progress_service),
) -> None:
    try:
        service.declare_program(user_id=current_user.id, degree_program_id=body.degree_program_id)
    except DegreeProgramNotFoundError as error:
        raise_degree_http_exception(error)


@router.get(
    "/degree-progress",
    response_model=DegreeProgressResponse,
    status_code=status.HTTP_200_OK,
    responses=DEGREE_ERROR_RESPONSES,
)
def get_degree_progress(
    current_user: User = Depends(get_current_user),
    service: DegreeRecommendationService = Depends(get_degree_recommendation_service),
) -> DegreeProgressResponse:
    try:
        progress, recommendations, unavailable_reason = service.recommend_next_courses(
            user_id=current_user.id
        )
    except NoDeclaredDegreeProgramError as error:
        raise_degree_http_exception(error)

    return DegreeProgressResponse(
        degree_program_id=progress.degree_program.id,
        degree_program_name=progress.degree_program.name,
        institution_name=progress.degree_program.institution_name,
        completed_credits=progress.completed_credits,
        completed_course_codes=sorted(progress.completed_course_codes),
        unmet_requirement_count=len(progress.unmet_requirements),
        eligible_courses=[
            EligibleCourseResponse(
                course_code=entry.course_code,
                course_name=entry.course_name,
                credits=entry.credits,
                category=entry.category,
            )
            for entry in progress.eligible_courses
        ],
        recommendations=recommendations,
        recommendations_unavailable_reason=unavailable_reason,
    )
