from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    PasswordResetRequestSchema,
    PasswordResetConfirmSchema,
    EmailVerificationConfirmSchema,
    MessageResponse,
    AccountDeletionRequest,
)

from app.services.account_deletion_service import delete_account
from app.services.auth_service import (
    register_user,
    login_user
)
from app.services.password_reset_service import (
    request_password_reset,
    confirm_password_reset,
)
from app.services.email_verification_service import (
    resend_verification_email,
    confirm_email_verification,
)
from app.services.token_service import (
    issue_refresh_token,
    rotate_refresh_token,
    revoke_refresh_token,
)
from app.api.auth import get_current_user
from app.api.rate_limit import rate_limiter
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.utils.jwt import create_access_token

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

REFRESH_COOKIE_NAME = "refresh_token"

# Named module-level dependencies (not inlined per-route) so tests can
# target the exact same callable via app.dependency_overrides.
register_rate_limit = rate_limiter(
    key_prefix="register", max_requests=5, window_seconds=60
)
login_rate_limit = rate_limiter(
    key_prefix="login", max_requests=20, window_seconds=60
)
password_reset_rate_limit = rate_limiter(
    key_prefix="password-reset", max_requests=5, window_seconds=60
)
verify_email_resend_rate_limit = rate_limiter(
    key_prefix="verify-email-resend", max_requests=5, window_seconds=60
)


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/auth",
    )


@router.post(
        "/register",
        response_model=TokenResponse
        )
def register(
    user: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(register_rate_limit),
):
    token, created_user = register_user(
        db=db,
        email=user.email,
        password=user.password,
        full_name=user.full_name
    )

    raw_refresh_token, _ = issue_refresh_token(db, created_user.id)
    _set_refresh_cookie(response, raw_refresh_token)

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
    response: Response,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(login_rate_limit),
):
    token, logged_in_user = login_user(
        db=db,
        email=user.email,
        password=user.password
    )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    raw_refresh_token, _ = issue_refresh_token(db, logged_in_user.id)
    _set_refresh_cookie(response, raw_refresh_token)

    return {"access_token": token,
            "token_type": "bearer"}


@router.post(
        "/refresh",
        response_model=TokenResponse
        )
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise HTTPException(
            status_code=401,
            detail="No refresh token provided",
        )

    new_raw_refresh_token, record = rotate_refresh_token(db, raw_refresh_token)
    _set_refresh_cookie(response, new_raw_refresh_token)

    access_token = create_access_token({"user_id": record.user_id})

    return {"access_token": access_token, "token_type": "bearer"}


@router.post(
        "/logout",
        response_model=MessageResponse,
        )
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        revoke_refresh_token(db, raw_refresh_token)

    _clear_refresh_cookie(response)
    return {"message": "Logged out"}


@router.get(
        "/me",
        response_model=UserResponse,
        )
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post(
        "/password-reset/request",
        response_model=MessageResponse,
        )
def password_reset_request(
    body: PasswordResetRequestSchema,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(password_reset_rate_limit),
):
    request_password_reset(db, body.email)
    return {
        "message": (
            "If an account with that email exists, a password reset "
            "link has been sent."
        )
    }


@router.post(
        "/password-reset/confirm",
        response_model=MessageResponse,
        )
def password_reset_confirm(
    body: PasswordResetConfirmSchema,
    db: Session = Depends(get_db),
):
    success = confirm_password_reset(db, body.token, body.new_password)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired password reset token",
        )
    return {"message": "Password has been reset"}


@router.post(
        "/verify-email/resend",
        response_model=MessageResponse,
        )
def verify_email_resend(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(verify_email_resend_rate_limit),
):
    resend_verification_email(db, current_user)
    return {"message": "Verification email sent"}


@router.post(
        "/verify-email/confirm",
        response_model=MessageResponse,
        )
def verify_email_confirm(
    body: EmailVerificationConfirmSchema,
    db: Session = Depends(get_db),
):
    success = confirm_email_verification(db, body.token)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token",
        )
    return {"message": "Email verified"}


@router.delete(
        "/account",
        response_model=MessageResponse,
        )
def delete_my_account(
    body: AccountDeletionRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_account(db, current_user, body.password)
    _clear_refresh_cookie(response)
    return {"message": "Account deleted"}
