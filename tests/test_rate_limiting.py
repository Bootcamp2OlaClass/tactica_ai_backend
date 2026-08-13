from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.auth import get_current_user
from app.api.rate_limit import rate_limiter, user_rate_limiter
from app.core.redis_client import get_redis_client
from app.db.session import get_db
from app.main import app
from app.routers.auth import login_rate_limit, register_rate_limit


@pytest.fixture(autouse=True)
def _clean_redis():
    # Real Redis (not mocked) — counters persist across the whole test
    # session, so each test must clear its own keys before asserting, since
    # every TestClient in this process shares the same "testclient" host.
    client = get_redis_client()
    client.flushdb()
    yield
    client.flushdb()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def register(client, email="student@example.com", password="Sup3rSecret!"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Ada Lovelace"},
    )


def test_register_endpoint_is_rate_limited_per_ip(client):
    responses = [
        register(client, email=f"student{i}@example.com") for i in range(6)
    ]

    statuses = [r.status_code for r in responses]
    assert statuses[:5] != [429] * 5
    assert 429 in statuses


def test_login_endpoint_is_rate_limited_per_ip(client):
    register(client)

    responses = [
        client.post(
            "/auth/login",
            json={"email": "student@example.com", "password": "wrong-password"},
        )
        for _ in range(21)
    ]

    statuses = [r.status_code for r in responses]
    # Login's own account-lockout feature (5 failed attempts -> 423) fires
    # well before the 20/min IP rate limit does, so requests 1-20 are a mix
    # of 401 (real auth decision) and 423 (lockout) -- never 429, since the
    # limiter's cap hasn't been reached yet.
    assert 429 not in statuses[:20]
    assert statuses[20] == 429


def test_rate_limit_is_scoped_per_endpoint_not_global(client):
    # Registered before exhausting the register limit, so this account
    # actually exists once we get to the login call below.
    register(client, email="separate@example.com")

    for i in range(5):
        register(client, email=f"filler{i}@example.com")
    exhausted_response = register(client, email="one-more@example.com")

    # Login has its own counter — exhausting register's must not affect it.
    login_response = client.post(
        "/auth/login",
        json={"email": "separate@example.com", "password": "Sup3rSecret!"},
    )

    assert exhausted_response.status_code == 429
    assert login_response.status_code == 200


def test_rate_limiter_fails_open_when_redis_unavailable():
    import redis as redis_module

    import app.api.rate_limit as rate_limit_module

    probe_app = FastAPI()
    unreachable_limit = rate_limiter(
        key_prefix="unreachable-probe", max_requests=1, window_seconds=60
    )

    @probe_app.get("/limited")
    def limited(_: None = Depends(unreachable_limit)):
        return {"ok": True}

    def _broken_client():
        raise redis_module.ConnectionError("simulated redis outage")

    original_get_client = rate_limit_module.get_redis_client
    probe_client = TestClient(probe_app, raise_server_exceptions=False)

    try:
        # rate_limit.py did `from app.core.redis_client import
        # get_redis_client`, so the name to patch is the one bound in *this*
        # module's namespace, not app.core.redis_client's.
        rate_limit_module.get_redis_client = _broken_client

        response = probe_client.get("/limited")
    finally:
        rate_limit_module.get_redis_client = original_get_client
        probe_client.close()

    assert response.status_code == 200


def test_user_rate_limiter_is_keyed_by_account_not_ip():
    probe_app = FastAPI()
    limited_dep = user_rate_limiter(
        key_prefix="probe-user-limit", max_requests=3, window_seconds=60
    )

    @probe_app.get("/limited")
    def limited(_: None = Depends(limited_dep)):
        return {"ok": True}

    probe_client = TestClient(probe_app, raise_server_exceptions=False)

    try:
        probe_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1001)
        first_user_statuses = [
            probe_client.get("/limited").status_code for _ in range(4)
        ]

        # A different account, same TestClient/IP, must have its own
        # untouched counter -- proves the key is user_id, not client host.
        probe_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1002)
        second_user_response = probe_client.get("/limited")
    finally:
        probe_client.close()
        probe_app.dependency_overrides.clear()

    assert first_user_statuses == [200, 200, 200, 429]
    assert second_user_response.status_code == 200
