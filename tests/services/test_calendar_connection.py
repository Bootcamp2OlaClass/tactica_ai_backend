from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import text

from app.models.calendar import CalendarConnection
from app.services.calendar_connection import CalendarConnectionService
from app.services.calendar_oauth import TokenSet
from tests.factories import create_user_with_course


class FakeOAuthService:
    def __init__(self, token_set=None):
        self._token_set = token_set or TokenSet(
            access_token="at-1", refresh_token="rt-1",
            expires_at=datetime.now(timezone.utc),
        )
        self.exchanged_codes = []

    def exchange_code_for_tokens(self, *, code):
        self.exchanged_codes.append(code)
        return self._token_set

    def get_authorization_url(self, *, state):
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"


def _build_service(db_session, *, oauth_service=None):
    return CalendarConnectionService(
        db=db_session, settings=SimpleNamespace(), oauth_service=oauth_service or FakeOAuthService()
    )


def test_connect_creates_a_new_connection(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="cal-conn-new")
    service = _build_service(db_session)

    connection = service.connect(user_id=user.id, code="auth-code")

    assert connection.access_token == "at-1"
    assert service.is_connected(user_id=user.id) is True


def test_connect_replaces_an_existing_connection(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="cal-conn-replace")
    oauth = FakeOAuthService(TokenSet(access_token="at-1", refresh_token="rt-1", expires_at=datetime.now(timezone.utc)))
    service = _build_service(db_session, oauth_service=oauth)
    service.connect(user_id=user.id, code="first-code")

    oauth._token_set = TokenSet(access_token="at-2", refresh_token="rt-2", expires_at=datetime.now(timezone.utc))
    service.connect(user_id=user.id, code="second-code")

    rows = db_session.query(CalendarConnection).filter(CalendarConnection.user_id == user.id).all()
    assert len(rows) == 1  # replaced, not duplicated
    assert rows[0].access_token == "at-2"


def test_disconnect_removes_the_connection(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="cal-conn-disconnect")
    service = _build_service(db_session)
    service.connect(user_id=user.id, code="auth-code")

    service.disconnect(user_id=user.id)

    assert service.is_connected(user_id=user.id) is False


def test_disconnect_when_never_connected_is_a_noop(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="cal-conn-noop")
    service = _build_service(db_session)

    service.disconnect(user_id=user.id)  # must not raise

    assert service.is_connected(user_id=user.id) is False


def test_tokens_are_encrypted_at_rest_not_stored_as_plaintext(db_session):
    user, _ = create_user_with_course(db_session, email_prefix="cal-conn-encrypted")
    service = _build_service(db_session)
    service.connect(user_id=user.id, code="auth-code")

    # Bypass the ORM/TypeDecorator entirely and read the raw column value,
    # the way a DB dump/leak would expose it -- it must not be "at-1".
    raw_access_token = db_session.execute(
        text("SELECT access_token FROM calendar_connections WHERE user_id = :uid"),
        {"uid": user.id},
    ).scalar_one()

    assert raw_access_token != "at-1"
    assert "at-1" not in raw_access_token
