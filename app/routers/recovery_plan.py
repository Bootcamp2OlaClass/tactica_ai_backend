from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.recovery_plan import RecoveryPlanResponse
from app.services.recovery_plan_generation import RecoveryPlanService

router = APIRouter(
    prefix="/api/v1",
    tags=["Recovery Plan"],
)


def get_recovery_plan_service(db: Session = Depends(get_db)) -> RecoveryPlanService:
    return RecoveryPlanService(db, get_settings())


@router.get(
    "/recovery-plan",
    response_model=RecoveryPlanResponse,
    status_code=status.HTTP_200_OK,
)
def get_recovery_plan(
    current_user: User = Depends(get_current_user),
    service: RecoveryPlanService = Depends(get_recovery_plan_service),
) -> RecoveryPlanResponse:
    """Computed live on every call -- deliberately not persisted (see
    PHASE_10_SMART_PLANNING.md's Implementation Notes for why). Cheap
    enough to compute synchronously: the deterministic pass is pure
    in-memory math over a bounded task list, and the optional LLM
    explanation pass is a single bounded call, the same latency profile
    as Phase 08's chat endpoint -- no Celery job needed."""
    return service.build_plan(user_id=current_user.id)
