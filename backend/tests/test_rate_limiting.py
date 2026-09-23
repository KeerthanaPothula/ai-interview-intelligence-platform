"""Tests for Phase 3 login rate limiting (app/core/rate_limit.py)."""

from types import SimpleNamespace

import pytest

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


# ---------------------------------------------------------------------------
# /auth/register — shares enforce_login_rate_limit with login/refresh/
# password-reset (see app/routers/auth.py). Registration is unauthenticated
# and hashes the password with bcrypt (deliberately CPU-expensive) before
# any other check runs, so an unlimited attacker could otherwise pin the
# CPU of this single-worker deployment with nothing more than repeated
# POSTs — the same abuse shape login rate limiting already exists for.
# ---------------------------------------------------------------------------


@pytest.fixture
def proxy_hops(monkeypatch):
    """Simulate N trusted reverse-proxy hops so X-Forwarded-For is honored.

    Local copy of the identical fixture in test_production_hardening.py —
    pytest fixtures aren't shared across files without a conftest.py entry,
    and duplicating this six-line helper is smaller than restructuring
    fixture location for one file.
    """

    def _set(n: int):
        monkeypatch.setattr(
            "app.core.client_ip.get_settings",
            lambda: SimpleNamespace(TRUSTED_PROXY_COUNT=n),
        )

    return _set


def _register_payload(email: str) -> dict:
    return {"email": email, "password": "securepassword1", "full_name": "Rate Limit Test"}


def test_register_allows_requests_within_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    for i in range(3):
        resp = client.post(
            "/api/v1/auth/register", json=_register_payload(f"within{i}@example.com")
        )
        assert resp.status_code == 201, resp.text

    get_settings.cache_clear()


def test_register_blocks_after_exceeding_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    for i in range(3):
        resp = client.post(
            "/api/v1/auth/register", json=_register_payload(f"reg{i}@example.com")
        )
        assert resp.status_code == 201, resp.text

    blocked = client.post(
        "/api/v1/auth/register", json=_register_payload("reg-blocked@example.com")
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    get_settings.cache_clear()


def test_register_within_limit_still_works_normally(client, monkeypatch):
    """Registration requests within the limit are entirely unaffected —
    same 201, same body shape, same duplicate-email 409 behavior."""
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "5")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    resp = client.post(
        "/api/v1/auth/register", json=_register_payload("within-limit@example.com")
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "within-limit@example.com"

    duplicate = client.post(
        "/api/v1/auth/register", json=_register_payload("within-limit@example.com")
    )
    assert duplicate.status_code == 409

    get_settings.cache_clear()


def test_register_rate_limit_is_independent_of_login(client, registered_user, monkeypatch):
    """Registration and login share the same limiter mechanism but are
    keyed separately by request.url.path — exhausting one endpoint's
    budget must not affect the other's."""
    monkeypatch.setenv("RATE_LIMIT_LOGIN_ATTEMPTS", "2")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    # Exhaust the login bucket for this IP.
    for _ in range(2):
        client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": "wrongpassword"},
        )
    login_blocked = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": "wrongpassword"},
    )
    assert login_blocked.status_code == 429

    # Registration's own (separate) bucket is untouched.
    register_resp = client.post(
        "/api/v1/auth/register", json=_register_payload("independent@example.com")
    )
    assert register_resp.status_code == 201

    get_settings.cache_clear()


def test_register_rate_limit_is_per_real_client_behind_a_proxy(client, proxy_hops):
    """Two different real clients (distinguished via X-Forwarded-For behind
    one trusted proxy hop) get independent registration rate-limit buckets
    — mirrors test_rate_limit_buckets_are_per_real_client_behind_a_proxy
    for /auth/login in test_production_hardening.py."""
    proxy_hops(1)

    def attempt(real_ip: str, email: str) -> int:
        return client.post(
            "/api/v1/auth/register",
            json=_register_payload(email),
            headers={"X-Forwarded-For": f"9.9.9.9, {real_ip}"},
        ).status_code

    for i in range(5):
        attempt("203.0.113.1", f"client-a-{i}@example.com")
    assert attempt("203.0.113.1", "client-a-blocked@example.com") == 429
    assert attempt("203.0.113.2", "client-b@example.com") == 201
