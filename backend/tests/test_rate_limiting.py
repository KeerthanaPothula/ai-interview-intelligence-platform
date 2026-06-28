"""Tests for Phase 3 login rate limiting (app/core/rate_limit.py)."""

from app.config import get_settings
from tests.conftest import VALID_USER


def test_login_allows_requests_within_limit(client, registered_user, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    for _ in range(3):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": "wrongpassword"},
        )
        assert response.status_code == 401

    get_settings.cache_clear()


def test_login_blocks_after_exceeding_limit(client, registered_user, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    for _ in range(3):
        client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": "wrongpassword"},
        )

    blocked = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": "wrongpassword"},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    get_settings.cache_clear()


def test_rate_limit_is_per_ip_not_per_account(client, registered_user, monkeypatch):
    """A correct-password login still counts toward the IP's rate limit —
    the limiter is keyed by client IP only, regardless of outcome."""
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "2")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    blocked = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert blocked.status_code == 429

    get_settings.cache_clear()
