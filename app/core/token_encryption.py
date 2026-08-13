"""Transparent at-rest encryption for OAuth tokens stored in the DB.

CalendarConnection's access/refresh tokens can't be one-way hashed like
RefreshToken is (app/utils/secure_tokens.py) -- the raw value must be
recoverable to call Google's API on the user's behalf. Symmetric
encryption is the mitigation for a raw DB dump/leak instead. The key is
derived from JWT_SECRET via a domain-separated hash rather than requiring
a brand-new required env var -- this repo has no real Google OAuth
credentials in use yet (Phase 12's own verification notes), so there's no
already-encrypted production data whose key would need migrating.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(
        f"calendar-token-encryption:{settings.JWT_SECRET}".encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedText(TypeDecorator):
    """A Text column that is encrypted at rest and transparently decrypted
    on read -- callers read/write plain strings exactly as before."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        try:
            return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "Stored token could not be decrypted -- JWT_SECRET may "
                "have changed since it was written."
            ) from exc
