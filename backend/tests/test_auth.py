"""
Integration tests for the /api/v1/auth endpoints.

Tests use the FastAPI TestClient (synchronous HTTPX transport) backed by
an in-memory SQLite database. Each test function gets a clean database
via the autouse reset_database fixture in conftest.py.
"""

import uuid

from app.models.user import User
from tests.conftest import VALID_USER


# ---------------------------------------------------------------------------
# POST /api/v1/auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_success_returns_201_and_user(self, client):
        response = client.post("/api/v1/auth/register", json=VALID_USER)

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == VALID_USER["email"]
        assert body["full_name"] == VALID_USER["full_name"]
        assert "id" in body
        assert "created_at" in body

    def test_password_not_returned(self, client):
        response = client.post("/api/v1/auth/register", json=VALID_USER)

        body = response.json()
        assert "password" not in body
        assert "hashed_password" not in body

    def test_duplicate_email_returns_409(self, client):
        client.post("/api/v1/auth/register", json=VALID_USER)
        response = client.post("/api/v1/auth/register", json=VALID_USER)

        assert response.status_code == 409

    def test_invalid_email_returns_422(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={**VALID_USER, "email": "not-an-email"},
        )
        assert response.status_code == 422

    def test_short_password_returns_422(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={**VALID_USER, "password": "short"},
        )
        assert response.status_code == 422

    def test_blank_full_name_returns_422(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={**VALID_USER, "full_name": "   "},
        )
        assert response.status_code == 422

    def test_missing_fields_returns_422(self, client):
        response = client.post("/api/v1/auth/register", json={"email": "x@example.com"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_success_returns_token(self, client, registered_user):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 20

    def test_wrong_password_returns_401(self, client, registered_user):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": "wrongpassword"},
        )
        assert response.status_code == 401

    def test_unknown_email_returns_401(self, client):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "anything"},
        )
        assert response.status_code == 401

    def test_wrong_and_unknown_same_response(self, client, registered_user):
        """Ensure wrong-password and unknown-email return the same status
        to prevent user enumeration attacks."""
        wrong_pw = client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": "wrongpassword"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "anything"},
        )
        assert wrong_pw.status_code == unknown.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me
# ---------------------------------------------------------------------------


class TestGetMe:
    def test_success_returns_user(self, client, auth_headers):
        response = client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == VALID_USER["email"]
        assert body["full_name"] == VALID_USER["full_name"]
        assert "id" in body

    def test_no_token_returns_401(self, client):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_malformed_token_returns_401(self, client):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.token"},
        )
        assert response.status_code == 401

    def test_wrong_scheme_returns_401(self, client, auth_token):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Basic {auth_token}"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/auth/me
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    def test_success_updates_full_name(self, client, auth_headers):
        response = client.patch(
            "/api/v1/auth/me",
            json={"full_name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["full_name"] == "Updated Name"
        assert body["email"] == VALID_USER["email"]

        # Persisted, not just echoed back.
        refetched = client.get("/api/v1/auth/me", headers=auth_headers)
        assert refetched.json()["full_name"] == "Updated Name"

    def test_no_token_returns_401(self, client):
        response = client.patch("/api/v1/auth/me", json={"full_name": "New Name"})
        assert response.status_code == 401

    def test_blank_full_name_returns_422(self, client, auth_headers):
        response = client.patch(
            "/api/v1/auth/me",
            json={"full_name": "   "},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_missing_full_name_returns_422(self, client, auth_headers):
        response = client.patch("/api/v1/auth/me", json={}, headers=auth_headers)
        assert response.status_code == 422

    def test_ignores_client_supplied_role_and_organization(self, client, auth_headers):
        """ProfileUpdateRequest has no role/organization_id field — extra
        fields are silently dropped by Pydantic (the default), so a client
        cannot escalate privilege or move itself into an organization by
        adding them to the request body. Mirrors
        test_registration_ignores_client_supplied_role in test_rbac.py."""
        response = client.patch(
            "/api/v1/auth/me",
            json={
                "full_name": "Still Me",
                "role": "super_admin",
                "organization_id": str(uuid.uuid4()),
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "candidate"
        assert body["organization"] is None

    def test_cannot_target_another_users_account(self, client, auth_headers, db):
        """There is no user_id anywhere in this request — updating always
        applies to whichever account the Bearer token belongs to. Register
        a second account and confirm the first token never touches it."""
        other = client.post(
            "/api/v1/auth/register",
            json={
                "email": "other-profile@example.com",
                "password": "securepassword1",
                "full_name": "Other Person",
            },
        )
        assert other.status_code == 201
        other_id = other.json()["id"]

        client.patch(
            "/api/v1/auth/me",
            json={"full_name": "Changed By Someone Else"},
            headers=auth_headers,
        )

        other_user = db.query(User).filter(User.id == uuid.UUID(other_id)).one()
        assert other_user.full_name == "Other Person"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout-all
# ---------------------------------------------------------------------------


class TestLogoutAllSessions:
    def test_success_returns_200(self, client, auth_headers):
        response = client.post("/api/v1/auth/logout-all", headers=auth_headers)
        assert response.status_code == 200
        assert "detail" in response.json()

    def test_no_token_returns_401(self, client):
        response = client.post("/api/v1/auth/logout-all")
        assert response.status_code == 401

    def test_invalidates_the_access_token_used_to_call_it(self, client, auth_headers):
        """The token_version bump must reject the very same access token on
        its next use — the core guarantee this endpoint exists for."""
        client.post("/api/v1/auth/logout-all", headers=auth_headers)

        still_using_old_token = client.get("/api/v1/auth/me", headers=auth_headers)
        assert still_using_old_token.status_code == 401

    def test_revokes_the_refresh_token(self, client, registered_user):
        login_resp = client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        tokens = login_resp.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        client.post("/api/v1/auth/logout-all", headers=headers)

        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 401

    def test_does_not_affect_other_users(self, client, auth_headers, db):
        """Logging out of all of *my* sessions must not touch anyone
        else's — token_version is per-user."""
        other = client.post(
            "/api/v1/auth/register",
            json={
                "email": "unaffected@example.com",
                "password": "securepassword1",
                "full_name": "Unaffected User",
            },
        )
        other_login = client.post(
            "/api/v1/auth/login",
            data={"username": "unaffected@example.com", "password": "securepassword1"},
        )
        other_token = other_login.json()["access_token"]

        client.post("/api/v1/auth/logout-all", headers=auth_headers)

        still_works = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {other_token}"}
        )
        assert still_works.status_code == 200


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "version" in data
