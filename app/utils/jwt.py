from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import get_settings


settings = get_settings()

ALGORITHM = "HS256"


def create_access_token(
        data: dict,
        expires_minutes: int = 60
):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
    )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=ALGORITHM
    )


def verify_token(token: str):

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[ALGORITHM]
        )

        return payload

    except JWTError:
        return None