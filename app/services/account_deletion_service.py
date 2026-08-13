from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.token_service import revoke_all_refresh_tokens_for_user
from app.utils.password import hash_password, verify_password
from app.utils.secure_tokens import generate_secure_token


def _now() -> datetime:
    return datetime.now(timezone.utc)


def delete_account(db: Session, user: User, password: str) -> None:
    """Soft-delete and anonymize the account.

    Deliberately anonymize-in-place rather than hard-delete: child rows
    across 25+ tables (documents, chunks, tasks, conversations, roadmaps,
    ...) use a mix of CASCADE and RESTRICT FK behavior (DocumentChunk is
    RESTRICT, see Phase 07), so a real cross-table hard delete needs a
    dedicated per-table cleanup pass. Anonymizing PII and revoking sessions
    satisfies "the account is gone" (can't log in, can't be identified by
    email/name) without that risk. A full hard-delete pass is tracked in
    BACKLOG.md as a follow-up, not done here.
    """
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account already deleted",
        )

    user.email = f"deleted-user-{user.id}@deleted.tacticaai.invalid"
    user.full_name = "Deleted User"
    # Unusable hash — nobody knows this random password, so even a stale
    # access token combined with a leaked hash can't be used to re-derive
    # credentials that still authenticate anywhere else.
    unusable_password, _ = generate_secure_token()
    user.password_hash = hash_password(unusable_password)
    user.deleted_at = _now()
    db.add(user)
    db.commit()

    revoke_all_refresh_tokens_for_user(db, user.id)
