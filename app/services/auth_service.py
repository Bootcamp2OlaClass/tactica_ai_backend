from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User

from app.utils.password import (
    hash_password,
    verify_password
)


from app.utils.jwt import(
    create_access_token
)

from app.core.config import get_settings
from app.services.email_service import get_email_service
from app.services.token_service import create_email_verification_token

settings = get_settings()


def _now():
    return datetime.now(timezone.utc)


def _send_verification_email(db: Session, user: User) -> None:
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


def register_user(
        db: Session,
        email: str,
        password: str,
        full_name: str,
):
    #check duplicate email
    existing_user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already exists"
        )
    #Hash password
    hashed_password = hash_password(password)

    #Create new user
    user = User(
        email=email,
        password_hash=hashed_password,
        full_name=full_name
    )

    #save user to database
    db.add(user)
    db.commit()
    db.refresh(user)

    _send_verification_email(db, user)

    #create JWT token after registration
    token = create_access_token({
        "user_id": user.id,
    })

    return token, user


def login_user(
        db: Session,
        email: str,
        password: str
):
    invalid_credentials = HTTPException(
        status_code=401,
        detail="Invalid credentials"
    )

    #Find user by email
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    #User does not exist
    if not user:
        raise invalid_credentials

    if user.locked_until is not None and user.locked_until > _now():
        raise HTTPException(
            status_code=423,
            detail=(
                "Account temporarily locked due to repeated failed "
                "login attempts. Try again later."
            ),
        )

    #Check password
    if not verify_password(
        password,
        user.password_hash
    ):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_max_failed_attempts:
            user.locked_until = _now() + timedelta(
                minutes=settings.login_lockout_minutes
            )
            user.failed_login_attempts = 0
        db.add(user)
        db.commit()
        raise invalid_credentials

    #Successful login resets lockout tracking
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    db.commit()
    db.refresh(user)

    #Create JWT token
    token = create_access_token({
        "user_id": user.id,
    })

    return token, user
