from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.exceptions.semester import SemesterConflictError
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard import DashboardService


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


def get_dashboard_service(
    db: Session = Depends(get_db),
) -> DashboardService:
    return DashboardService(db)


@router.get(
    "",
    response_model=DashboardSummaryResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Authentication required or invalid",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "Multiple semesters are marked active",
        },
    },
    summary="Get the authenticated user's dashboard summary",
)
def get_dashboard(
    current_user: User = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummaryResponse:
    try:
        result = service.get_summary(user_id=current_user.id)
    except SemesterConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return DashboardSummaryResponse(**result)
