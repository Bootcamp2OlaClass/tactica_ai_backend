import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.utils.secure_tokens import generate_secure_token, hash_token

settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Refresh tokens -------------------------------------------------------

def issue_refresh_token(
    db: Session,
    user_id: int,
    family_id: uuid.UUID | None = None,
) -> tuple[str, RefreshToken]:
    raw_token, token_hash = generate_secure_token()
    record = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw_token, record


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[str, RefreshToken]:
    """Validate and rotate a refresh token, detecting reuse of an already-used token.

    If the presented token was already revoked (i.e. it was already rotated
    away once before), the entire token family is revoked — this is the
    standard signal that a refresh token was stolen and replayed.
    """
    token_hash = hash_token(raw_token)
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )

    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    if record is None:
        raise invalid

    if record.revoked_at is not None:
        _revoke_family(db, record.family_id)
        raise invalid

    if record.expires_at < _now():
        raise invalid

    record.revoked_at = _now()
    db.add(record)

    new_raw_token, new_record = issue_refresh_token(
        db, record.user_id, family_id=record.family_id
    )
    db.commit()
    return new_raw_token, new_record


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = hash_token(raw_token)
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = _now()
        db.add(record)
        db.commit()


def revoke_all_refresh_tokens_for_user(db: Session, user_id: int) -> None:
    (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .update({"revoked_at": _now()})
    )
    db.commit()


def _revoke_family(db: Session, family_id: uuid.UUID) -> None:
    (
        db.query(RefreshToken)
        .filter(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .update({"revoked_at": _now()})
    )
    db.commit()


# --- Password reset tokens -------------------------------------------------

def create_password_reset_token(db: Session, user_id: int) -> str:
    raw_token, token_hash = generate_secure_token()
    record = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=_now()
        + timedelta(minutes=settings.password_reset_token_expire_minutes),
    )
    db.add(record)
    db.commit()
    return raw_token


def consume_password_reset_token(db: Session, raw_token: str) -> int | None:
    token_hash = hash_token(raw_token)
    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )

    if (
        record is None
        or record.used_at is not None
        or record.expires_at < _now()
    ):
        return None

    record.used_at = _now()
    db.add(record)
    db.commit()
    return record.user_id


# --- Email verification tokens ---------------------------------------------

def create_email_verification_token(db: Session, user_id: int) -> str:
    raw_token, token_hash = generate_secure_token()
    record = EmailVerificationToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=_now()
        + timedelta(hours=settings.email_verification_token_expire_hours),
    )
    db.add(record)
    db.commit()
    return raw_token


def consume_email_verification_token(db: Session, raw_token: str) -> int | None:
    token_hash = hash_token(raw_token)
    record = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == token_hash)
        .first()
    )

    if (
        record is None
        or record.used_at is not None
        or record.expires_at < _now()
    ):
        return None

    record.used_at = _now()
    db.add(record)
    db.commit()
    return record.user_id
