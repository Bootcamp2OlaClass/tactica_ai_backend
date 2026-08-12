from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services.email_service import get_email_service
from app.services.token_service import (
    create_email_verification_token,
    consume_email_verification_token,
)

settings = get_settings()


def resend_verification_email(db: Session, user: User) -> None:
    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already verified",
        )

    raw_token = create_email_verification_token(db, user.id)
    get_email_service().send(
        to=user.email,
        subject="Verify your Tactica AI email",
        body=(
            "Confirm your email address using this token: "
            f"{raw_token}\n\n"
            f"This token expires in {settings.email_verification_token_expire_hours} hours."
        ),
    )


def confirm_email_verification(db: Session, raw_token: str) -> bool:
    user_id = consume_email_verification_token(db, raw_token)
    if user_id is None:
        return False

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return False

    user.email_verified = True
    db.add(user)
    db.commit()
    return True
