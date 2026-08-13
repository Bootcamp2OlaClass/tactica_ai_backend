import logging
from collections.abc import Callable

import redis
from fastapi import Depends, HTTPException, Request, status

from app.api.auth import get_current_user
from app.core.redis_client import get_redis_client
from app.models.user import User

logger = logging.getLogger(__name__)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_rate_limit(key: str, *, max_requests: int, window_seconds: int) -> None:
    try:
        client = get_redis_client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
    except redis.RedisError:
        logger.warning("Rate limiter unavailable (Redis error) for %s; failing open", key)
        return

    if count > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


def rate_limiter(
    *, key_prefix: str, max_requests: int, window_seconds: int
) -> Callable[[Request], None]:
    """Fixed-window rate limit dependency, keyed by client IP.

    Backed by Redis (already required infra for Celery/caching) rather than
    in-process state, so limits hold across the multiple worker processes a
    real deployment runs. Fails OPEN on Redis errors — matching this
    codebase's existing stance that Redis is optional infrastructure the app
    degrades gracefully without (see /health in app/main.py) — a Redis
    outage should not become an accidental full API outage on top of it.

    Returns a plain function (not a closure created per-request) so tests
    can target it directly via app.dependency_overrides.
    """

    def _check(request: Request) -> None:
        key = f"ratelimit:{key_prefix}:{_client_key(request)}"
        _check_rate_limit(key, max_requests=max_requests, window_seconds=window_seconds)

    return _check


def user_rate_limiter(
    *, key_prefix: str, max_requests: int, window_seconds: int
) -> Callable[..., None]:
    """Fixed-window rate limit dependency, keyed by authenticated user id
    rather than client IP.

    Used for authenticated, per-request-expensive endpoints (a synchronous
    LLM call) where the IP a request arrives from is a weaker signal than
    the account making it — many legitimate users can share an IP (NAT,
    shared network), and an authenticated abuser can trivially rotate IPs
    but not accounts.
    """

    def _check(current_user: User = Depends(get_current_user)) -> None:
        key = f"ratelimit:{key_prefix}:user:{current_user.id}"
        _check_rate_limit(key, max_requests=max_requests, window_seconds=window_seconds)

    return _check
