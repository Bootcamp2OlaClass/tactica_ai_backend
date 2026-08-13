from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.roadmap import (
    RoadmapError,
    RoadmapGenerationAlreadyInProgressError,
    RoadmapItemNotFoundError,
    RoadmapNotFoundError,
    RoadmapQueueUnavailableError,
)
from app.exceptions.semester import SemesterNotFoundError
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.roadmap import (
    RoadmapItemResponse,
    RoadmapItemUpdateRequest,
    RoadmapResponse,
)
from app.services.roadmap_generation_trigger import RoadmapGenerationTriggerService
from app.services.roadmap_item_update import RoadmapItemUpdateService
from app.services.roadmap_query import RoadmapQueryService

router = APIRouter(
    prefix="/api/v1",
    tags=["Roadmap"],
)

ROADMAP_ERROR_RESPONSES = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorResponse,
        "description": "Authentication required or invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorResponse,
        "description": "Semester, roadmap, or roadmap item not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Roadmap generation already in progress",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Roadmap generation could not be queued",
    },
}


def get_roadmap_generation_trigger_service(
    db: Session = Depends(get_db),
) -> RoadmapGenerationTriggerService:
    return RoadmapGenerationTriggerService(db)


def get_roadmap_query_service(db: Session = Depends(get_db)) -> RoadmapQueryService:
    return RoadmapQueryService(db)


def get_roadmap_item_update_service(
    db: Session = Depends(get_db),
) -> RoadmapItemUpdateService:
    return RoadmapItemUpdateService(db)


def raise_roadmap_http_exception(error: Exception) -> NoReturn:
    if isinstance(
        error,
        (SemesterNotFoundError, RoadmapNotFoundError, RoadmapItemNotFoundError),
    ):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, RoadmapGenerationAlreadyInProgressError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, RoadmapQueueUnavailableError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(status_code=status_code, detail=str(error)) from error


@router.post(
    "/semesters/{semester_id}/roadmap/generate",
    response_model=RoadmapResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ROADMAP_ERROR_RESPONSES,
)
def trigger_roadmap_generation(
    semester_id: int = Path(ge=1, description="ID of the semester to generate a roadmap for"),
    current_user: User = Depends(get_current_user),
    service: RoadmapGenerationTriggerService = Depends(
        get_roadmap_generation_trigger_service
    ),
) -> RoadmapResponse:
    """Triggers generation if none exists yet, or regenerates an existing
    one -- the same endpoint serves both per this phase's minimal-API
    scope note; a 409 covers the only real conflict (already running)."""
    try:
        roadmap = service.trigger_generation(semester_id=semester_id, user_id=current_user.id)
        return RoadmapResponse.model_validate(roadmap)
    except (SemesterNotFoundError, RoadmapError) as error:
        raise_roadmap_http_exception(error)


@router.get(
    "/semesters/{semester_id}/roadmap",
    response_model=RoadmapResponse,
    status_code=status.HTTP_200_OK,
    responses=ROADMAP_ERROR_RESPONSES,
)
def get_semester_roadmap(
    semester_id: int = Path(ge=1, description="ID of the semester"),
    current_user: User = Depends(get_current_user),
    service: RoadmapQueryService = Depends(get_roadmap_query_service),
) -> RoadmapResponse:
    try:
        roadmap = service.get_roadmap(semester_id=semester_id, user_id=current_user.id)
        return RoadmapResponse.model_validate(roadmap)
    except (SemesterNotFoundError, RoadmapError) as error:
        raise_roadmap_http_exception(error)


@router.patch(
    "/roadmap-items/{item_id}",
    response_model=RoadmapItemResponse,
    status_code=status.HTTP_200_OK,
    responses=ROADMAP_ERROR_RESPONSES,
)
def update_roadmap_item(
    body: RoadmapItemUpdateRequest,
    item_id: int = Path(ge=1, description="ID of the roadmap item to edit"),
    current_user: User = Depends(get_current_user),
    service: RoadmapItemUpdateService = Depends(get_roadmap_item_update_service),
) -> RoadmapItemResponse:
    try:
        item = service.update_item(
            item_id=item_id,
            user_id=current_user.id,
            title=body.title,
            description=body.description,
        )
        return RoadmapItemResponse.model_validate(item)
    except RoadmapError as error:
        raise_roadmap_http_exception(error)
