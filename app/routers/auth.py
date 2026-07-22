from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse
)

from app.services.auth_service import (
    register_user,
    login_user
)
from app.db.session import get_db

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.post(
        "/register",
        response_model=TokenResponse
        )
def register(
    user: RegisterRequest,
    db: Session = Depends(get_db)
):
    token = register_user(
        db=db,
        email=user.email,
        password=user.password,
        full_name=user.full_name
    )
    return {
        "access_token": token,
        "token_type": "bearer"
    }

@router.post(
        "/login",
        response_model=TokenResponse
        )
def login(
    user: LoginRequest,
    db: Session = Depends(get_db)
):
    token = login_user(
        db=db,
        email=user.email,
        password=user.password
    )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    return {"access_token": token,
            "token_type": "bearer"}