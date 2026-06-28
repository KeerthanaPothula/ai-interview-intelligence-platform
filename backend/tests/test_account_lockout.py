"""Tests for Phase 3 account lockout with progressive backoff
(app/services/auth_service.py, app/routers/auth.py)."""

from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.models.user import User
from tests.conftest import VALID_USER


def _fail_login(client):
    return client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": "wrongpassword"},
    )


def test_account_locks_after_threshold_failures(client, registered_user, monkeypatch):
    monkeypatch.setenv("ACCOUNT_LOCKOUT_THRESHOLD", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "100")
    get_settings.cache_clear()

    for _ in range(3):
        resp = _fail_login(client)
        assert resp.status_code == 401

    locked = _fail_login(client)
    assert locked.status_code == 423

    get_settings.cache_clear()


def test_locked_account_rejects_correct_password(client, registered_user, monkeypatch):
    monkeypatch.setenv("ACCOUNT_LOCKOUT_THRESHOLD", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "100")
    get_settings.cache_clear()

    for _ in range(3):
        _fail_login(client)

    response = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 423

    get_settings.cache_clear()


def test_lockout_expires_and_account_unlocks(client, registered_user, db, monkeypatch):
    monkeypatch.setenv("ACCOUNT_LOCKOUT_THRESHOLD", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "100")
    get_settings.cache_clear()

    for _ in range(3):
        _fail_login(client)

    # Simulate the lockout window having already elapsed.
    user = db.query(User).filter(User.email == VALID_USER["email"]).first()
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    response = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 200

    get_settings.cache_clear()


def test_successful_login_resets_failed_attempt_counter(
    client, registered_user, db, monkeypatch
):
    monkeypatch.setenv("ACCOUNT_LOCKOUT_THRESHOLD", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "100")
    get_settings.cache_clear()

    _fail_login(client)
    _fail_login(client)

    success = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert success.status_code == 200

    user = db.query(User).filter(User.email == VALID_USER["email"]).first()
    assert user.failed_login_attempts == 0

    get_settings.cache_clear()


def test_progressive_backoff_doubles_lockout_duration(
    client, registered_user, db, monkeypatch
):
    """Second lockout for the same account uses double the base duration."""
    monkeypatch.setenv("ACCOUNT_LOCKOUT_THRESHOLD", "3")
    monkeypatch.setenv("ACCOUNT_LOCKOUT_DURATION_MINUTES", "15")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "100")
    get_settings.cache_clear()

    for _ in range(3):
        _fail_login(client)

    user = db.query(User).filter(User.email == VALID_USER["email"]).first()
    # SQLite (used by this test suite) does not reliably preserve
    # tz-awareness on DateTime(timezone=True) columns when read back via
    # the ORM, so locked_until can come back naive even though it was
    # written as UTC-aware — normalize before arithmetic against an
    # aware datetime.now(timezone.utc).
    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    first_lockout_duration = locked_until - datetime.now(timezone.utc)
    assert user.lockout_count == 1
    assert timedelta(minutes=14) < first_lockout_duration <= timedelta(minutes=15)

    # Expire the first lockout and trigger a second one.
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    for _ in range(3):
        _fail_login(client)

    db.refresh(user)
    locked_until = user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    second_lockout_duration = locked_until - datetime.now(timezone.utc)
    assert user.lockout_count == 2
    assert timedelta(minutes=29) < second_lockout_duration <= timedelta(minutes=30)

    get_settings.cache_clear()
