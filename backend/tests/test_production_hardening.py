"""Regression tests for the production-readiness audit fixes.

Each test documents one hardening fix and fails against the pre-fix code:
data isolation, credential-rotation semantics, privilege boundaries, upload
limits, error-message disclosure and deployment/config behaviour.
"""

import asyncio
import inspect
import io
import json
import logging
import smtplib
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from fastapi import HTTPException, Request, UploadFile
from starlette.datastructures import Headers

from app.config import Settings, get_settings
from app.core.ai_reliability import call_gemini_with_retry
from app.core.client_ip import get_client_ip
from app.core.exceptions import AIServiceError
from app.models.role import Role
from app.models.user import User
from app.routers import auth as auth_router
from app.routers import documents as documents_router
from app.services import auth_service, upload_service
from tests.conftest import (
    RECRUITER_USER,
    VALID_USER,
    _login,
    _register_with_role,
)
from tests.test_recruiter import _make_completed_session


def _login_tokens(client, user_data: dict) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": user_data["email"], "password": user_data["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Data isolation: a recruiter with no organization must fail CLOSED
# ---------------------------------------------------------------------------


@pytest.fixture
def orgless_recruiter_headers(client, db):
    """A RECRUITER whose organization_id is NULL — reachable in practice when a
    Super Admin promotes an unaffiliated candidate via PATCH /users/{id}/role."""
    _register_with_role(
        client, db, RECRUITER_USER, role=Role.RECRUITER.value, organization_id=None
    )
    return {"Authorization": f"Bearer {_login(client, RECRUITER_USER)}"}


def test_recruiter_without_organization_sees_no_candidates(
    client, db, org_candidate, orgless_recruiter_headers
):
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.get(
        "/api/v1/recruiter/candidates", headers=orgless_recruiter_headers
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


def test_recruiter_without_organization_cannot_change_candidate_status(
    client, db, org_candidate, orgless_recruiter_headers
):
    session = _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "hired"},
        headers=orgless_recruiter_headers,
    )

    assert response.status_code == 404
    db.refresh(session)
    assert session.recruiter_status != "hired"


# ---------------------------------------------------------------------------
# Credential rotation: changing a password must revoke refresh tokens
# ---------------------------------------------------------------------------


def test_change_password_revokes_existing_refresh_tokens(client, registered_user):
    tokens = _login_tokens(client, VALID_USER)

    changed = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": VALID_USER["password"],
            "new_password": "a-brand-new-password-1",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert changed.status_code == 200

    # A stolen refresh token must not keep minting valid access tokens.
    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401


def test_refresh_rejects_deactivated_account(client, db, registered_user):
    tokens = _login_tokens(client, VALID_USER)
    user = db.get(User, uuid.UUID(registered_user["id"]))
    user.is_active = False
    db.commit()

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Privilege boundary: only a Super Admin may (de)activate privileged accounts
# ---------------------------------------------------------------------------


def test_admin_cannot_deactivate_super_admin(client, admin_headers, super_admin_user):
    response = client.patch(
        f"/api/v1/admin/users/{super_admin_user['id']}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_deactivate_another_admin(client, db, admin_headers):
    other_admin = _register_with_role(
        client,
        db,
        {
            "email": "admin2@example.com",
            "password": "securepassword9",
            "full_name": "Second Admin",
        },
        role=Role.ADMIN.value,
    )

    response = client.patch(
        f"/api/v1/admin/users/{other_admin['id']}/deactivate", headers=admin_headers
    )

    assert response.status_code == 403


def test_super_admin_can_deactivate_admin(client, db, super_admin_headers, admin_user):
    response = client.patch(
        f"/api/v1/admin/users/{admin_user['id']}/deactivate",
        headers=super_admin_headers,
    )

    assert response.status_code == 200
    assert db.get(User, uuid.UUID(admin_user["id"])).is_active is False


def test_admin_can_still_deactivate_recruiter(client, admin_headers, recruiter_user):
    response = client.patch(
        f"/api/v1/admin/users/{recruiter_user['id']}/deactivate",
        headers=admin_headers,
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Upload limits: never load an oversized body into memory in full
# ---------------------------------------------------------------------------


class _CountingBytesIO(io.BytesIO):
    """BytesIO that records how many bytes callers actually pulled out."""

    total_read = 0

    def read(self, size=-1):
        data = super().read(size)
        self.total_read += len(data)
        return data


def test_audio_validation_reads_at_most_the_size_cap(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "1")
    get_settings.cache_clear()
    payload = _CountingBytesIO(b"RIFF" + b"x" * (8 * 1024 * 1024))
    upload = UploadFile(
        file=payload,
        filename="answer.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    try:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(upload_service.validate_upload(upload))
    finally:
        get_settings.cache_clear()

    assert exc.value.status_code == 413
    # 1 MB cap (+1 byte to detect the overflow) — not the 8 MB body.
    assert payload.total_read <= 1024 * 1024 + 1


def test_resume_upload_endpoint_does_not_block_the_event_loop():
    """CPU-bound extraction/embedding must run in the threadpool: a plain
    `def` endpoint is dispatched there, an `async def` one would stall /health."""
    assert not inspect.iscoroutinefunction(documents_router.upload_resume)


def test_resume_extraction_failure_hides_internals_and_removes_file(
    client, auth_headers, upload_dir, monkeypatch
):
    def _boom(file_path, mime_type):
        raise RuntimeError(f"Package not found at '{file_path}'")

    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text", _boom
    )
    pdf = io.BytesIO(b"%PDF-1.4 " + b"x" * 2048)

    response = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.pdf", pdf, "application/pdf")},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert str(upload_dir) not in response.text
    assert "Package not found" not in response.text
    assert list(upload_dir.rglob("*.pdf")) == []


# ---------------------------------------------------------------------------
# Information disclosure: /ready is unauthenticated
# ---------------------------------------------------------------------------


def test_ready_does_not_leak_database_error_details(client, monkeypatch):
    def _broken_session():
        raise RuntimeError(
            'connection to server at "10.1.2.3", port 5432 failed: '
            'FATAL: password authentication failed for user "aiip_user"'
        )

    monkeypatch.setattr("app.main.SessionLocal", _broken_session)

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.text
    assert "10.1.2.3" not in body
    assert "aiip_user" not in body
    assert response.json()["checks"]["database"]["ok"] is False


# ---------------------------------------------------------------------------
# Gemini reliability: any transport fault is retried and mapped to AIServiceError
# ---------------------------------------------------------------------------


class _FastRetrySettings:
    GEMINI_MAX_RETRIES = 3
    GEMINI_RETRY_BACKOFF_SECONDS = 0.001


@pytest.fixture
def fast_retries(monkeypatch):
    monkeypatch.setattr(
        "app.core.ai_reliability.get_settings", lambda: _FastRetrySettings()
    )


@pytest.mark.parametrize(
    "error", [httpx.ConnectError("refused"), httpx.RemoteProtocolError("dropped")]
)
def test_gemini_retries_connection_level_errors(fast_retries, error):
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise error
        return "recovered"

    assert call_gemini_with_retry(flaky, operation="test op") == "recovered"
    assert attempts["n"] == 3


def test_gemini_persistent_connection_error_becomes_ai_service_error(fast_retries):
    def down():
        raise httpx.ConnectError("refused")

    with pytest.raises(AIServiceError) as exc:
        call_gemini_with_retry(down, operation="test op")

    assert exc.value.status_code == 502


# ---------------------------------------------------------------------------
# Password reset: previously untested critical path
# ---------------------------------------------------------------------------


@pytest.fixture
def sent_reset_emails(monkeypatch):
    """Capture (email, url) instead of sending; runs as a background task."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        auth_router,
        "_send_reset_email",
        lambda email, url, logger, settings: sent.append((email, url)),
    )
    return sent


def test_forgot_password_gives_same_answer_for_known_and_unknown_emails(
    client, registered_user, sent_reset_emails
):
    known = client.post(
        "/api/v1/auth/forgot-password", json={"email": VALID_USER["email"]}
    )
    unknown = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [email for email, _ in sent_reset_emails] == [VALID_USER["email"]]


def test_forgot_password_is_rate_limited(client, sent_reset_emails):
    statuses = [
        client.post(
            "/api/v1/auth/forgot-password", json={"email": f"user{i}@example.com"}
        ).status_code
        for i in range(8)
    ]

    assert statuses[0] == 200
    assert 429 in statuses


def test_reset_password_flow_sets_new_password_and_revokes_sessions(
    client, registered_user, sent_reset_emails
):
    tokens = _login_tokens(client, VALID_USER)
    client.post("/api/v1/auth/forgot-password", json={"email": VALID_USER["email"]})
    reset_token = sent_reset_emails[0][1].rsplit("/", 1)[1]

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "brand-new-password-2"},
    )
    assert reset.status_code == 200

    new_login = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": "brand-new-password-2"},
    )
    assert new_login.status_code == 200
    replay = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    # Single use: the same token cannot be redeemed twice.
    again = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "another-password-3"},
    )
    assert again.status_code == 400


def _reset_email_settings(environment: str):
    return SimpleNamespace(
        ENVIRONMENT=environment,
        SMTP_HOST=None,
        SMTP_PORT=587,
        SMTP_USER="",
        SMTP_FROM="x",
    )


def test_reset_url_is_never_logged_in_production(caplog):
    url = "https://app.example.com/reset-password/SECRET-TOKEN-123"

    with caplog.at_level(logging.DEBUG):
        auth_router._send_reset_email(
            "victim@example.com",
            url,
            logging.getLogger("t"),
            _reset_email_settings("production"),
        )

    assert "SECRET-TOKEN-123" not in caplog.text
    assert "NOT" in caplog.text  # operators are told the email was not sent


def test_reset_url_is_still_logged_in_development(caplog):
    url = "http://localhost:5173/reset-password/DEV-TOKEN-456"

    with caplog.at_level(logging.DEBUG):
        auth_router._send_reset_email(
            "dev@example.com",
            url,
            logging.getLogger("t"),
            _reset_email_settings("development"),
        )

    assert "DEV-TOKEN-456" in caplog.text


def test_smtp_connection_has_a_timeout(monkeypatch):
    captured = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            pass

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    settings = SimpleNamespace(
        ENVIRONMENT="production",
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=587,
        SMTP_USER="",
        SMTP_PASSWORD="",
        SMTP_FROM="noreply@example.com",
    )

    auth_router._send_reset_email(
        "a@example.com", "https://x/reset-password/t", logging.getLogger("t"), settings
    )

    assert captured["timeout"] and captured["timeout"] <= 30


# ---------------------------------------------------------------------------
# Login timing: unknown email costs the same bcrypt work as a wrong password
# ---------------------------------------------------------------------------


def test_login_for_unknown_email_still_runs_a_password_hash_check(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        auth_service,
        "verify_password",
        lambda plain, hashed: calls.append(hashed) or False,
    )

    assert auth_service.authenticate_user(db, "nobody@example.com", "any-pw") is None
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Client IP behind a reverse proxy
# ---------------------------------------------------------------------------


def _request(peer: str, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request(
        {
            "type": "http",
            "headers": headers,
            "client": (peer, 1234),
            "method": "GET",
            "path": "/",
        }
    )


@pytest.fixture
def proxy_hops(monkeypatch):
    def _set(n: int):
        monkeypatch.setattr(
            "app.core.client_ip.get_settings",
            lambda: SimpleNamespace(TRUSTED_PROXY_COUNT=n),
        )

    return _set


def test_forwarded_header_is_ignored_by_default(proxy_hops):
    proxy_hops(0)
    assert get_client_ip(_request("10.0.0.1", "203.0.113.9")) == "10.0.0.1"


def test_client_ip_is_taken_from_the_trusted_side_of_forwarded_for(proxy_hops):
    proxy_hops(1)
    # The left entry is attacker-controlled; only the proxy-appended right one counts.
    assert get_client_ip(_request("10.0.0.1", "6.6.6.6, 203.0.113.9")) == "203.0.113.9"


def test_client_ip_falls_back_to_peer_when_header_is_missing(proxy_hops):
    proxy_hops(1)
    assert get_client_ip(_request("10.0.0.1")) == "10.0.0.1"
    proxy_hops(2)
    assert get_client_ip(_request("10.0.0.1", "203.0.113.9")) == "10.0.0.1"


def test_rate_limit_buckets_are_per_real_client_behind_a_proxy(client, proxy_hops):
    proxy_hops(1)

    def attempt(real_ip: str) -> int:
        return client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong-password"},
            headers={"X-Forwarded-For": f"9.9.9.9, {real_ip}"},
        ).status_code

    for _ in range(5):
        attempt("203.0.113.1")
    assert attempt("203.0.113.1") == 429  # that client is throttled...
    assert attempt("203.0.113.2") == 401  # ...but a different client is not


# ---------------------------------------------------------------------------
# Production configuration guards
# ---------------------------------------------------------------------------


def _production_settings(**overrides) -> Settings:
    values = dict(
        ENVIRONMENT="production",
        DEBUG=False,
        DATABASE_URL="postgresql+psycopg2://u:p@db.example.com/app",
        JWT_SECRET_KEY="9f3c1a7e5b2d4c6f8a0e1b3d5f7a9c2e4b6d8f0a1c3e5b7d9f1a3c5e7b9d1f3a",
        GEMINI_API_KEY="k",
        CORS_ORIGINS="https://app.example.com",
    )
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _production_settings(CORS_ORIGINS="*")


def test_production_rejects_copied_env_example_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        _production_settings(
            JWT_SECRET_KEY="replace_with_64_char_hex_secret_generated_via_openssl_rand_hex_32"
        )


def test_production_accepts_a_sane_configuration():
    settings = _production_settings()
    assert settings.CORS_ORIGINS == ["https://app.example.com"]


def test_development_still_allows_placeholder_values():
    settings = Settings(
        DATABASE_URL="sqlite://",
        JWT_SECRET_KEY="replace_with_64_char_hex_secret_generated_via_openssl_rand_hex_32",
        GEMINI_API_KEY="k",
        CORS_ORIGINS="*",
    )
    assert settings.ENVIRONMENT == "development"


# ---------------------------------------------------------------------------
# Deployment files
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_hands_pid1_to_uvicorn():
    """`cmd1 && uvicorn ...` leaves the shell as PID 1, which does not forward
    SIGTERM — Render's graceful-shutdown signal would never reach the server."""
    dockerfile = (_REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    cmd = [line for line in dockerfile.splitlines() if line.startswith("CMD")][-1]
    assert "exec uvicorn" in cmd


def test_render_blueprint_declares_the_frontend_url_and_safe_cors():
    render = yaml.safe_load((_REPO_ROOT / "render.yaml").read_text(encoding="utf-8"))
    env = {e["key"]: e for e in render["services"][0]["envVars"]}

    assert "FRONTEND_URL" in env  # password-reset links must not fall back to localhost
    assert env["CORS_ORIGINS"].get("value") != "*"
    assert env["DEBUG"]["value"] is False


def test_vercel_config_sets_baseline_security_headers():
    config = json.loads(
        (_REPO_ROOT / "frontend" / "vercel.json").read_text(encoding="utf-8")
    )
    headers = {
        h["key"]: h["value"] for rule in config["headers"] for h in rule["headers"]
    }

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in headers
