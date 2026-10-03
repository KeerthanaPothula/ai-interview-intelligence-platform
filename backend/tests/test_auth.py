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
        assert other.status_code == 201, other.text
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


# ---------------------------------------------------------------------------
# Email addresses are matched case-insensitively
# ---------------------------------------------------------------------------

_TYPED = "Alice.Smith@Example.COM"  # stored as Alice.Smith@example.com
_PW = "securepassword1"


def _register_typed(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": _TYPED, "password": _PW, "full_name": "Alice Smith"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _login_as(client, username, password=_PW):
    return client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )


class TestEmailCaseInsensitivity:
    def test_login_with_the_address_exactly_as_registered(self, client):
        _register_typed(client)
        assert _login_as(client, _TYPED).status_code == 200

    def test_login_with_a_different_case(self, client):
        _register_typed(client)
        for variant in ("alice.smith@example.com", " ALICE.SMITH@EXAMPLE.COM "):
            assert _login_as(client, variant).status_code == 200, variant

    def test_registering_a_case_variant_is_a_duplicate(self, client, db):
        _register_typed(client)
        dup = client.post(
            "/api/v1/auth/register",
            json={
                "email": "alice.smith@example.com",
                "password": "anotherpassword2",
                "full_name": "Second Alice",
            },
        )
        assert dup.status_code == 409
        assert db.query(User).count() == 1

    def test_wrong_password_with_a_case_variant_counts_against_the_account(
        self, client, db
    ):
        created = _register_typed(client)
        assert (
            _login_as(client, "alice.smith@example.com", "wrongpass1").status_code
            == 401
        )
        db.expire_all()
        user = db.get(User, uuid.UUID(created["id"]))
        assert user.failed_login_attempts == 1

    def test_forgot_password_with_a_case_variant_reaches_the_account(self, client, db):
        from app.models.password_reset_token import PasswordResetToken

        created = _register_typed(client)
        resp = client.post(
            "/api/v1/auth/forgot-password", json={"email": "alice.smith@example.com"}
        )
        assert resp.status_code == 200
        tokens = db.query(PasswordResetToken).filter_by(
            user_id=uuid.UUID(created["id"])
        )
        assert tokens.count() == 1

    def test_exact_match_wins_over_existing_case_variant_duplicates(self, client, db):
        """Accounts that already differ only by case (created before this
        check) each keep logging in with their own exact address."""
        from app.core.security import get_password_hash

        for email, pw in (
            ("bob@example.com", "lowerpassword1"),
            ("Bob@example.com", "upperpassword1"),
        ):
            db.add(
                User(
                    email=email,
                    hashed_password=get_password_hash(pw),
                    full_name="Bob",
                )
            )
        db.commit()

        assert _login_as(client, "bob@example.com", "lowerpassword1").status_code == 200
        assert _login_as(client, "Bob@example.com", "upperpassword1").status_code == 200
        assert _login_as(client, "bob@example.com", "upperpassword1").status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/change-password — current-password guessing is throttled
# ---------------------------------------------------------------------------


def _change_password(client, headers, current, new="a-brand-new-password-1"):
    return client.post(
        "/api/v1/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


class TestChangePasswordBruteForce:
    """A stolen access token must not allow unlimited online guessing of the
    current password (which would turn a temporary token into a permanent
    account takeover). Wrong guesses share login's per-account lockout."""

    def _threshold(self):
        from app.config import get_settings

        return get_settings().ACCOUNT_LOCKOUT_THRESHOLD

    def test_wrong_guesses_lock_the_account(self, client, auth_headers, db):
        for _ in range(self._threshold()):
            resp = _change_password(client, auth_headers, "wrong-guess-123")
            assert resp.status_code == 400

        # Locked: even the correct current password is refused, and the
        # password is unchanged.
        locked = _change_password(client, auth_headers, VALID_USER["password"])
        assert locked.status_code == 423
        db.expire_all()
        user = db.query(User).filter(User.email == VALID_USER["email"]).one()
        assert user.locked_until is not None

    def test_lockout_also_blocks_login(self, client, auth_headers):
        for _ in range(self._threshold()):
            _change_password(client, auth_headers, "wrong-guess-123")
        login = client.post(
            "/api/v1/auth/login",
            data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert login.status_code == 423

    def test_a_correct_change_resets_the_failure_count(self, client, auth_headers, db):
        for _ in range(self._threshold() - 1):
            _change_password(client, auth_headers, "wrong-guess-123")

        ok = _change_password(client, auth_headers, VALID_USER["password"])
        assert ok.status_code == 200, ok.text
        db.expire_all()
        user = db.query(User).filter(User.email == VALID_USER["email"]).one()
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    def test_correct_current_password_still_works_first_time(
        self, client, auth_headers
    ):
        ok = _change_password(client, auth_headers, VALID_USER["password"])
        assert ok.status_code == 200, ok.text
        relogin = client.post(
            "/api/v1/auth/login",
            data={
                "username": VALID_USER["email"],
                "password": "a-brand-new-password-1",
            },
        )
        assert relogin.status_code == 200
