import hashlib
import secrets


def generate_secure_token() -> tuple[str, str]:
    """Generate an opaque token for emailing/cookie use plus its stored hash.

    The raw token is only ever sent to the client (cookie, email link) and
    never persisted — only its SHA-256 hash is stored, so a leaked database
    can't be used to replay refresh/reset/verification tokens.
    """
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_token(raw_token)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
