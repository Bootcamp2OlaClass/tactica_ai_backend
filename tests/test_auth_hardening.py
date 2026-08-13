from app.api.authorization import require_roles
from app.db.session import get_db
from app.main import app
from app.models.email_verification_token import EmailVerificationToken
from app.models.user import User, UserRole
from app.routers.auth import (
    login_rate_limit,
    password_reset_rate_limit,
    register_rate_limit,
    verify_email_resend_rate_limit,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    def _no_rate_limit():
        return None

    app.dependency_overrides[get_db] = override_get_db
    # These tests exercise auth *logic*, not the rate limiter itself (that
    # has its own dedicated tests in test_rate_limiting.py) — without this
    # override, every test in this file would share one Redis counter keyed
    # by TestClient's fixed "testclient" host and could trip 429s depending
    # on run order/count, which isn't what any of these tests are about.
    app.dependency_overrides[register_rate_limit] = _no_rate_limit
    app.dependency_overrides[login_rate_limit] = _no_rate_limit
    app.dependency_overrides[password_reset_rate_limit] = _no_rate_limit
    app.dependency_overrides[verify_email_resend_rate_limit] = _no_rate_limit
    test_client = TestClient(app, raise_server_exceptions=False)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()


def register(client, email="student@example.com", password="Sup3rSecret!"):
    return client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Ada Lovelace"},
    )


def test_register_issues_access_token_and_refresh_cookie(client):
    response = register(client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert "refresh_token" in response.cookies


def test_register_leaves_email_unverified(client, db_session):
    register(client)

    user = db_session.query(User).filter(User.email == "student@example.com").first()
    assert user.email_verified is False


def test_login_wrong_password_returns_401(client):
    register(client)

    response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_locks_account_after_max_failed_attempts(client, db_session):
    register(client)

    for _ in range(5):
        client.post(
            "/auth/login",
            json={"email": "student@example.com", "password": "wrong-password"},
        )

    locked_response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "Sup3rSecret!"},
    )

    assert locked_response.status_code == 423

    user = db_session.query(User).filter(User.email == "student@example.com").first()
    assert user.locked_until is not None


def test_login_success_resets_failed_attempts(client, db_session):
    register(client)
    client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
    )

    response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "Sup3rSecret!"},
    )

    assert response.status_code == 200
    user = db_session.query(User).filter(User.email == "student@example.com").first()
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_refresh_rotates_token_and_issues_new_access_token(client):
    register(client)
    old_refresh_cookie = client.cookies.get("refresh_token")

    response = client.post("/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]
    new_refresh_cookie = response.cookies.get("refresh_token")
    assert new_refresh_cookie is not None
    assert new_refresh_cookie != old_refresh_cookie


def test_refresh_without_cookie_is_rejected(client):
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_reusing_a_rotated_refresh_token_revokes_the_whole_family(client):
    register(client)
    original_refresh_token = client.cookies.get("refresh_token")

    # First rotation succeeds and moves the client onto a new token.
    first_refresh = client.post("/auth/refresh")
    assert first_refresh.status_code == 200
    current_refresh_token = client.cookies.get("refresh_token")
    assert current_refresh_token != original_refresh_token

    # Replaying the now-stale original token is reuse of an already-rotated
    # token — must be rejected...
    client.cookies.set("refresh_token", original_refresh_token)
    reuse_response = client.post("/auth/refresh")
    assert reuse_response.status_code == 401

    # ...and must revoke the entire family, so even the legitimately-rotated
    # current token from the same family no longer works either.
    client.cookies.set("refresh_token", current_refresh_token)
    after_reuse_response = client.post("/auth/refresh")
    assert after_reuse_response.status_code == 401


def test_logout_revokes_refresh_token(client):
    register(client)

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200

    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401


def test_me_requires_a_valid_access_token(client):
    unauthenticated = client.get("/auth/me")
    assert unauthenticated.status_code in (401, 403)

    register_response = register(client)
    access_token = register_response.json()["access_token"]

    authenticated = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert authenticated.status_code == 200
    body = authenticated.json()
    assert body["email"] == "student@example.com"
    assert body["email_verified"] is False


def test_password_reset_request_does_not_reveal_whether_email_exists(client):
    existing = client.post(
        "/auth/password-reset/request", json={"email": "nobody@example.com"}
    )
    register(client)
    known = client.post(
        "/auth/password-reset/request", json={"email": "student@example.com"}
    )

    assert existing.status_code == 200
    assert known.status_code == 200
    assert existing.json() == known.json()


def test_password_reset_confirm_with_invalid_token_fails(client):
    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "NewPassw0rd!"},
    )
    assert response.status_code == 400


def test_password_reset_end_to_end_changes_password_and_revokes_sessions(
    client, db_session
):
    register(client)
    user = db_session.query(User).filter(User.email == "student@example.com").first()

    from app.services.token_service import create_password_reset_token

    raw_token = create_password_reset_token(db_session, user.id)

    confirm_response = client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "BrandNewPassw0rd!"},
    )
    assert confirm_response.status_code == 200

    # Old refresh session must no longer work post-reset.
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401

    # New password logs in successfully.
    login_response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "BrandNewPassw0rd!"},
    )
    assert login_response.status_code == 200

    # A reset token can only be used once.
    reuse_response = client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "AnotherPassw0rd!"},
    )
    assert reuse_response.status_code == 400


def test_password_reset_clears_an_existing_login_lockout(client, db_session):
    register(client)
    for _ in range(5):
        client.post(
            "/auth/login",
            json={"email": "student@example.com", "password": "wrong-password"},
        )
    user = db_session.query(User).filter(User.email == "student@example.com").first()
    assert user.locked_until is not None

    from app.services.token_service import create_password_reset_token

    raw_token = create_password_reset_token(db_session, user.id)
    confirm_response = client.post(
        "/auth/password-reset/confirm",
        json={"token": raw_token, "new_password": "BrandNewPassw0rd!"},
    )
    assert confirm_response.status_code == 200

    login_response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "BrandNewPassw0rd!"},
    )
    assert login_response.status_code == 200

    db_session.refresh(user)
    assert user.locked_until is None
    assert user.failed_login_attempts == 0


def test_email_verification_end_to_end(client, db_session):
    register_response = register(client)
    access_token = register_response.json()["access_token"]
    user = db_session.query(User).filter(User.email == "student@example.com").first()

    verification_token = (
        db_session.query(EmailVerificationToken)
        .filter(EmailVerificationToken.user_id == user.id)
        .first()
    )
    assert verification_token is not None

    from app.services.token_service import create_email_verification_token

    raw_token = create_email_verification_token(db_session, user.id)

    confirm_response = client.post(
        "/auth/verify-email/confirm", json={"token": raw_token}
    )
    assert confirm_response.status_code == 200

    me_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_response.json()["email_verified"] is True

    resend_after_verified = client.post(
        "/auth/verify-email/resend",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resend_after_verified.status_code == 409


def test_email_verification_confirm_with_invalid_token_fails(client):
    response = client.post(
        "/auth/verify-email/confirm", json={"token": "not-a-real-token"}
    )
    assert response.status_code == 400


def test_rbac_denies_non_admin_user(db_session):
    # require_roles() has no production caller yet (no admin-only endpoint
    # exists in the real API surface), so this exercises the dependency
    # directly against a throwaway app rather than a real router — see
    # BUGS.md 2026-08-13 for why the old /rbac/admin-only test route was
    # removed from app.main instead of kept around for this test alone.
    probe_app = FastAPI()

    @probe_app.get("/admin-only")
    def admin_only(current_user: User = Depends(require_roles(UserRole.ADMIN))):
        return {"user_id": current_user.id}

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    probe_app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app, raise_server_exceptions=False)
    probe_client = TestClient(probe_app, raise_server_exceptions=False)

    register(test_client)

    login_response = test_client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "Sup3rSecret!"},
    )
    access_token = login_response.json()["access_token"]

    response = probe_client.get(
        "/admin-only", headers={"Authorization": f"Bearer {access_token}"}
    )

    test_client.close()
    probe_client.close()
    app.dependency_overrides.clear()

    assert response.status_code == 403


def test_account_deletion_requires_correct_password(client):
    register_response = register(client)
    access_token = register_response.json()["access_token"]

    response = client.request(
        "DELETE",
        "/auth/account",
        json={"password": "wrong-password"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401


def test_account_deletion_anonymizes_and_revokes_sessions(client, db_session):
    register_response = register(client)
    access_token = register_response.json()["access_token"]
    original_refresh_cookie = client.cookies.get("refresh_token")

    response = client.request(
        "DELETE",
        "/auth/account",
        json={"password": "Sup3rSecret!"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert "refresh_token" not in response.cookies

    user = db_session.query(User).first()
    assert user.deleted_at is not None
    assert user.email != "student@example.com"
    assert user.full_name == "Deleted User"

    # The now-stale access token must stop working immediately, not just
    # after its natural expiry — deleted_at is checked on every request.
    me_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_response.status_code == 401

    # The refresh token issued before deletion must be revoked too.
    client.cookies.set("refresh_token", original_refresh_cookie)
    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401

    # Logging in with the old (pre-anonymization) email must fail exactly
    # like a nonexistent account — deletion status isn't distinguishable.
    login_response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "Sup3rSecret!"},
    )
    assert login_response.status_code == 401


def test_account_deletion_frees_email_for_reregistration(client):
    register(client)
    login_response = client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "Sup3rSecret!"},
    )
    access_token = login_response.json()["access_token"]

    client.request(
        "DELETE",
        "/auth/account",
        json={"password": "Sup3rSecret!"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    re_register_response = register(client)
    assert re_register_response.status_code == 200


def test_account_deletion_twice_fails_because_token_is_already_dead(client):
    # A deleted account can't authenticate at all (see the deleted_at check
    # in get_current_user), so this can never reach delete_account's own
    # "already deleted" 409 branch through the API — that branch only
    # guards direct/internal callers. Documented here so the dead-looking
    # path in account_deletion_service.py isn't mistaken for unreachable
    # dead code and removed.
    register_response = register(client)
    access_token = register_response.json()["access_token"]

    client.request(
        "DELETE",
        "/auth/account",
        json={"password": "Sup3rSecret!"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    second_response = client.request(
        "DELETE",
        "/auth/account",
        json={"password": "Sup3rSecret!"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert second_response.status_code == 401
