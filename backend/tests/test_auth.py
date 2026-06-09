"""
Integration tests for the /api/v1/auth endpoints.

Tests use the FastAPI TestClient (synchronous HTTPX transport) backed by
an in-memory SQLite database. Each test function gets a clean database
via the autouse reset_database fixture in conftest.py.
"""

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
# GET /health
# ---------------------------------------------------------------------------


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "version" in data
