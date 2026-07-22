from fastapi import APIRouter, Depends

from app.api.authorization import require_roles
from app.models.user import User, UserRole

router = APIRouter(
    prefix="/rbac",
    tags=["RBAC Test"],
)


@router.get("/admin-only")
def admin_only(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    return {
        "message": "Admin access granted",
        "user_id": current_user.id,
        "role": current_user.role,
    }