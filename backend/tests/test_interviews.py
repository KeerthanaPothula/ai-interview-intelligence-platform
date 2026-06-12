import uuid

from app.models.interview import (
    InterviewSession,
    SESSION_STATUS_DRAFT,
    SESSION_STATUS_IN_PROGRESS,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_VALID_SESSION = {
    "title": "Backend Interview",
    "job_role": "Backend Engineer",
    # Must be >= 20 chars (SessionCreate.job_description min_length=20)
    "job_description": "Build scalable backend APIs using Python, FastAPI, and PostgreSQL.",
}

_USER_B = {
    "email": "bob@example.com",
    "password": "securepassword2",
    "full_name": "Bob Example",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_get_headers(client, user_data: dict) -> dict:
    """Register a user and return their Bearer auth headers."""
    client.post("/api/v1/auth/register", json=user_data)
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": user_data["email"], "password": user_data["password"]},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_session(client, headers: dict, title: str = "Test Session") -> dict:
    """Create a session via the API and return its JSON response."""
    resp = client.post(
        "/api/v1/interviews/",
        json={**_VALID_SESSION, "title": title},
        headers=headers,
    )
    assert resp.status_code == 201, f"Session creation failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# TestCreateSession
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_create_returns_201(self, client, auth_headers):
        response = client.post(
            "/api/v1/interviews/",
            json=_VALID_SESSION,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == _VALID_SESSION["title"]
        assert data["job_role"] == _VALID_SESSION["job_role"]
        assert data["status"] == SESSION_STATUS_DRAFT
        assert data["questions"] == []
        assert data["response_count"] == 0

    def test_create_requires_auth(self, client):
        response = client.post("/api/v1/interviews/", json=_VALID_SESSION)
        assert response.status_code == 401

    def test_create_missing_fields_returns_422(self, client, auth_headers):
        # job_description is a required field — omitting it must yield 422
        response = client.post(
            "/api/v1/interviews/",
            json={"title": "Missing Description", "job_role": "Engineer"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_short_job_description_returns_422(self, client, auth_headers):
        # job_description min_length=20 — "Build APIs" (9 chars) must fail
        response = client.post(
            "/api/v1/interviews/",
            json={**_VALID_SESSION, "job_description": "Build APIs"},
            headers=auth_headers,
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestListSessions
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_list_empty_returns_empty_list(self, client, auth_headers):
        response = client.get("/api/v1/interviews/", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_list_returns_only_own_sessions(
        self, client, auth_headers, interview_session
    ):
        # interview_session belongs to user A (the registered_user / auth_headers user)
        # Create user B with their own session — must not appear in user A's list
        b_headers = _register_and_get_headers(client, _USER_B)
        _create_session(client, b_headers, title="User B Session")

        response = client.get("/api/v1/interviews/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # User A sees exactly one session — their own
        assert len(data) == 1
        assert data[0]["id"] == str(interview_session.id)

    def test_list_respects_skip_and_limit(self, client, auth_headers):
        # Create 3 sessions for the same user
        for i in range(3):
            _create_session(client, auth_headers, title=f"Session {i + 1}")

        response = client.get(
            "/api/v1/interviews/",
            params={"skip": 1, "limit": 1},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.json()) == 1


# ---------------------------------------------------------------------------
# TestGetSession
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_get_returns_session_with_questions_and_response_count(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        audio_response,
    ):
        response = client.get(
            f"/api/v1/interviews/{interview_session.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(interview_session.id)
        assert data["status"] == SESSION_STATUS_DRAFT
        # Questions list — interview_question fixture created 1 question
        assert len(data["questions"]) == 1
        assert data["questions"][0]["body"] == interview_question.body
        assert data["questions"][0]["sequence_order"] == 1
        # response_count — audio_response fixture created 1 response
        assert data["response_count"] == 1

    def test_get_not_found_returns_404(self, client, auth_headers):
        response = client.get(
            f"/api/v1/interviews/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_other_users_session_returns_404(self, client, auth_headers):
        # User B creates a session — user A must not be able to retrieve it
        b_headers = _register_and_get_headers(client, _USER_B)
        b_session = _create_session(client, b_headers)

        response = client.get(
            f"/api/v1/interviews/{b_session['id']}",
            headers=auth_headers,
        )
        # Must be 404, never 403 — ownership mismatch is indistinguishable from
        # non-existence from the caller's perspective
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestUpdateSession
# ---------------------------------------------------------------------------


class TestUpdateSession:
    def test_update_draft_returns_200(self, client, auth_headers, interview_session):
        response = client.patch(
            f"/api/v1/interviews/{interview_session.id}",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    def test_update_non_draft_returns_409(
        self, client, auth_headers, interview_session, db
    ):
        # Directly advance the session status past draft in the DB.
        # db and interview_session share the same db fixture instance within
        # this test — the update is visible to the router's DB session.
        db.query(InterviewSession).filter(
            InterviewSession.id == interview_session.id
        ).update({"status": SESSION_STATUS_IN_PROGRESS})
        db.commit()

        response = client.patch(
            f"/api/v1/interviews/{interview_session.id}",
            json={"title": "Should Be Rejected"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_update_other_users_session_returns_404(self, client, auth_headers):
        b_headers = _register_and_get_headers(client, _USER_B)
        b_session = _create_session(client, b_headers)

        response = client.patch(
            f"/api/v1/interviews/{b_session['id']}",
            json={"title": "Stolen Title"},
            headers=auth_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestDeleteSession
# ---------------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_returns_204(self, client, auth_headers, interview_session):
        response = client.delete(
            f"/api/v1/interviews/{interview_session.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204
        assert response.content == b""

        # The session must no longer be retrievable
        get_response = client.get(
            f"/api/v1/interviews/{interview_session.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    def test_delete_other_users_session_returns_404(self, client, auth_headers):
        b_headers = _register_and_get_headers(client, _USER_B)
        b_session = _create_session(client, b_headers)

        response = client.delete(
            f"/api/v1/interviews/{b_session['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 404
