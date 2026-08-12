from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services.email_service import get_email_service
from app.services.token_service import (
    create_password_reset_token,
    consume_password_reset_token,
)
from app.services.token_service import revoke_all_refresh_tokens_for_user
from app.utils.password import hash_password

settings = get_settings()


def request_password_reset(db: Session, email: str) -> None:
    """Always succeeds silently — does not reveal whether the email exists."""
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        return

    raw_token = create_password_reset_token(db, user.id)
    get_email_service().send(
        to=user.email,
        subject="Reset your Tactica AI password",
        body=(
            "Reset your password using this token: "
            f"{raw_token}\n\n"
            f"This token expires in {settings.password_reset_token_expire_minutes} minutes."
        ),
    )


def confirm_password_reset(db: Session, raw_token: str, new_password: str) -> bool:
    user_id = consume_password_reset_token(db, raw_token)
    if user_id is None:
        return False

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return False

    user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()

    # A password change invalidates every existing session.
    revoke_all_refresh_tokens_for_user(db, user.id)
    return True
