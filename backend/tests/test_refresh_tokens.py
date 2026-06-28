"""Tests for Phase 3 refresh token issuance, rotation, revocation, logout,
and token-version invalidation."""

from app.models.user import User
from tests.conftest import VALID_USER


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestLoginIssuesRefreshToken:
    def test_login_returns_refresh_token(self, client, registered_user):
        body = _login(client)
        assert "refresh_token" in body
        assert isinstance(body["refresh_token"], str)
        assert len(body["refresh_token"]) > 20

    def test_login_flow_still_returns_access_token(self, client, registered_user):
        """Backward compatibility: pre-Phase-3 clients reading only
        access_token/token_type must still work unchanged."""
        body = _login(client)
        assert "access_token" in body
        assert body["token_type"] == "bearer"


class TestRefreshEndpoint:
    def test_refresh_returns_new_token_pair(self, client, registered_user):
        tokens = _login(client)
        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 200
        new_tokens = response.json()
        assert new_tokens["access_token"] != tokens["access_token"]
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    def test_rotated_token_works_for_authenticated_requests(
        self, client, registered_user
    ):
        tokens = _login(client)
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refreshed['access_token']}"},
        )
        assert me.status_code == 200

    def test_old_refresh_token_rejected_after_rotation(self, client, registered_user):
        tokens = _login(client)
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        replay = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401

    def test_reusing_rotated_token_revokes_the_new_one_too(
        self, client, registered_user
    ):
        """Replaying an already-rotated refresh token is treated as a
        theft signal: every other active token for the user is revoked,
        including the new one issued by the rotation."""
        tokens = _login(client)
        rotated = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()

        # Replay the original (already-rotated-away) token.
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

        # The token issued by the rotation should now also be revoked.
        second_attempt = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
        )
        assert second_attempt.status_code == 401

    def test_invalid_refresh_token_returns_401(self, client):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not-a-real-token-00000000000000"},
        )
        assert response.status_code == 401

    def test_malformed_refresh_token_returns_422(self, client):
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "short"})
        assert response.status_code == 422


class TestLogout:
    def test_logout_returns_200(self, client, registered_user):
        tokens = _login(client)
        response = client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 200

    def test_logged_out_refresh_token_cannot_be_reused(self, client, registered_user):
        tokens = _login(client)
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )

        response = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 401

    def test_logout_does_not_invalidate_current_access_token(
        self, client, registered_user
    ):
        """Logout revokes the refresh token only — the access token remains
        valid until it naturally expires (stateless JWT design)."""
        tokens = _login(client)
        client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me.status_code == 200


class TestTokenVersioning:
    def test_bumping_token_version_invalidates_existing_access_tokens(
        self, client, registered_user, db
    ):
        tokens = _login(client)

        user = db.query(User).filter(User.email == VALID_USER["email"]).first()
        user.token_version += 1
        db.commit()

        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me.status_code == 401

    def test_new_login_after_version_bump_issues_valid_token(
        self, client, registered_user, db
    ):
        user = db.query(User).filter(User.email == VALID_USER["email"]).first()
        user.token_version += 1
        db.commit()

        tokens = _login(client)
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me.status_code == 200
