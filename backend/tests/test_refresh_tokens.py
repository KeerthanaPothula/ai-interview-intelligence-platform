"""Tests for Phase 3 refresh token issuance, rotation, revocation, logout,
and token-version invalidation."""

from datetime import timedelta

from app.config import get_settings
from app.core.security import hash_refresh_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.conftest import VALID_USER


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _refresh(client, raw):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": raw})


def _row(db, raw) -> RefreshToken:
    db.expire_all()
    return (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(raw))
        .one()
    )


def _age_rotation_past_grace(db, raw):
    """Move `raw`'s rotation to just outside the two-tab grace window."""
    row = _row(db, raw)
    grace = get_settings().REFRESH_TOKEN_REUSE_GRACE_SECONDS
    row.revoked_at = row.revoked_at - timedelta(seconds=grace + 1)
    db.commit()


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

    def test_old_refresh_token_rejected_after_rotation(
        self, client, registered_user, db
    ):
        tokens = _login(client)
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        _age_rotation_past_grace(db, tokens["refresh_token"])
        replay = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401

    def test_reusing_rotated_token_revokes_the_new_one_too(
        self, client, registered_user, db
    ):
        """Replaying an already-rotated refresh token (outside the two-tab
        grace window) is treated as a theft signal: every other active token
        for the user is revoked, including the new one issued by the
        rotation."""
        tokens = _login(client)
        rotated = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).json()
        _age_rotation_past_grace(db, tokens["refresh_token"])

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


class TestTwoTabRefreshRace:
    """Two tabs that read the same stored refresh token before either's
    refresh returned both redeem it, moments apart."""

    def test_near_simultaneous_refreshes_both_succeed(
        self, client, registered_user, db
    ):
        shared = _login(client)["refresh_token"]

        tab_a = _refresh(client, shared)
        tab_b = _refresh(client, shared)

        assert tab_a.status_code == 200, tab_a.text
        assert tab_b.status_code == 200, tab_b.text
        a, b = tab_a.json(), tab_b.json()
        assert a["refresh_token"] != b["refresh_token"]
        for tokens in (a, b):  # neither tab was logged out
            me = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            assert me.status_code == 200
            assert _refresh(client, tokens["refresh_token"]).status_code == 200

    def test_grace_redemptions_do_not_extend_the_window(
        self, client, registered_user, db
    ):
        shared = _login(client)["refresh_token"]
        _refresh(client, shared)
        first_rotation = _row(db, shared).revoked_at

        assert _refresh(client, shared).status_code == 200
        assert _row(db, shared).revoked_at == first_rotation

    def test_reuse_after_the_window_is_still_theft(self, client, registered_user, db):
        shared = _login(client)["refresh_token"]
        rotated = _refresh(client, shared).json()
        _age_rotation_past_grace(db, shared)

        assert _refresh(client, shared).status_code == 401
        # Every session was revoked, including the legitimate rotation.
        assert _refresh(client, rotated["refresh_token"]).status_code == 401

    def test_no_grace_once_the_successor_is_logged_out(
        self, client, registered_user, db
    ):
        """Inside the window, but the token it rotated into was revoked by a
        logout: replaying the old token is not a racing tab, so it is theft."""
        tokens = _login(client)
        shared = tokens["refresh_token"]
        rotated = _refresh(client, shared).json()
        client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": rotated["refresh_token"]},
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )

        assert _refresh(client, shared).status_code == 401

    def test_no_grace_after_theft_response_revoked_everything(
        self, client, registered_user, db
    ):
        older = _login(client)["refresh_token"]
        newer = _refresh(client, older).json()["refresh_token"]
        _age_rotation_past_grace(db, older)
        assert _refresh(client, older).status_code == 401  # theft: revoke all

        # `newer` was rotated into nothing; a fresh replay of it gets no grace.
        assert _refresh(client, newer).status_code == 401

    def test_logout_with_a_just_rotated_token_gets_no_grace(
        self, client, registered_user, db
    ):
        """The grace is for /auth/refresh only; logout keeps the strict rule."""
        tokens = _login(client)
        shared = tokens["refresh_token"]
        rotated = _refresh(client, shared).json()

        resp = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": shared},
            headers={"Authorization": f"Bearer {rotated['access_token']}"},
        )

        assert resp.status_code == 401
        assert _refresh(client, rotated["refresh_token"]).status_code == 401

    def test_zero_grace_disables_it(self, client, registered_user, monkeypatch):
        monkeypatch.setenv("REFRESH_TOKEN_REUSE_GRACE_SECONDS", "0")
        get_settings.cache_clear()
        try:
            shared = _login(client)["refresh_token"]
            _refresh(client, shared)
            assert _refresh(client, shared).status_code == 401
        finally:
            get_settings.cache_clear()


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
