import uuid

from fastapi import HTTPException

from app.models.interview import (
    Question,
    QUESTION_SOURCE_AI_GENERATED,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_USER_B = {
    "email": "bob@example.com",
    "password": "securepassword2",
    "full_name": "Bob Example",
}

_VALID_SESSION_B = {
    "title": "User B Interview",
    "job_role": "Data Scientist",
    "job_description": "Machine learning pipelines using Python and TensorFlow.",
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


# ---------------------------------------------------------------------------
# TestGenerateQuestions
# ---------------------------------------------------------------------------


class TestGenerateQuestions:
    def test_generate_returns_questions(
        self, client, auth_headers, interview_session, mock_gemini_questions
    ):
        # mock_gemini_questions patches generate_questions to return 6 dicts
        # without making any real Gemini API call.
        response = client.post(
            f"/api/v1/interviews/{interview_session.id}/questions/generate",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 6
        # Every item must expose the three required fields.
        first = data[0]
        assert "body" in first
        assert "category" in first
        assert "sequence_order" in first

    def test_generate_replaces_existing(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        mock_gemini_questions,
        db,
    ):
        # interview_question created 1 question in the DB with sequence_order=1.
        # Call generate twice — each call must replace ALL existing questions,
        # not append to them. After two calls the DB must contain exactly 6 rows.

        client.post(
            f"/api/v1/interviews/{interview_session.id}/questions/generate",
            headers=auth_headers,
        )
        client.post(
            f"/api/v1/interviews/{interview_session.id}/questions/generate",
            headers=auth_headers,
        )

        # db and the client both use TestingSessionLocal with StaticPool — they
        # share the same underlying connection, so committed data is immediately
        # visible to this query.
        count = (
            db.query(Question)
            .filter(Question.session_id == interview_session.id)
            .count()
        )
        # 1 original + 6 + 6 = 13 would mean appending; 6 means replace-on-each-call.
        assert count == 6

    def test_generate_session_not_found_returns_404(
        self, client, auth_headers, mock_gemini_questions
    ):
        response = client.post(
            f"/api/v1/interviews/{uuid.uuid4()}/questions/generate",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_generate_other_users_session_returns_404(
        self, client, auth_headers, mock_gemini_questions
    ):
        # User B creates a session. User A attempts to generate questions for it.
        b_headers = _register_and_get_headers(client, _USER_B)
        resp = client.post(
            "/api/v1/interviews/",
            json=_VALID_SESSION_B,
            headers=b_headers,
        )
        assert resp.status_code == 201
        b_session_id = resp.json()["id"]

        response = client.post(
            f"/api/v1/interviews/{b_session_id}/questions/generate",
            headers=auth_headers,
        )
        # Ownership mismatch must produce 404, never 403 — the caller cannot
        # distinguish a missing session from one belonging to another user.
        assert response.status_code == 404

    def test_generate_gemini_error_returns_502(
        self, client, auth_headers, interview_session, monkeypatch
    ):
        # Simulate the HTTPException(502) that gemini_service raises on API
        # failures (network error, invalid JSON, empty response).
        #
        # Why HTTPException(502) and not RuntimeError:
        #   question_service.generate_and_save() does not wrap exceptions from
        #   generate_questions in a try/except. gemini_service always raises
        #   HTTPException (502 or 503) — never a bare RuntimeError. Patching
        #   to raise RuntimeError would produce HTTP 500 (FastAPI's default
        #   for unhandled exceptions), causing this assertion to fail.
        #
        # Why patch app.services.question_service.generate_questions:
        #   question_service does `from app.services.gemini_service import
        #   generate_questions`, creating a local name binding. Patching
        #   gemini_service.generate_questions after import has no effect on
        #   that local reference. The correct target is the name as it lives
        #   in question_service's own namespace.

        def _raise_502(job_role, job_description, count):
            raise HTTPException(status_code=502, detail="Gemini unavailable")

        monkeypatch.setattr(
            "app.services.question_service.generate_questions",
            _raise_502,
        )

        response = client.post(
            f"/api/v1/interviews/{interview_session.id}/questions/generate",
            headers=auth_headers,
        )
        assert response.status_code == 502


# ---------------------------------------------------------------------------
# TestListQuestions
# ---------------------------------------------------------------------------


class TestListQuestions:
    def test_list_ordered_by_sequence_order(
        self, client, auth_headers, interview_session, db
    ):
        # Insert questions in a deliberately shuffled sequence_order to prove
        # the endpoint sorts by sequence_order ASC — not insertion order.
        for seq_order in (3, 1, 2):
            db.add(
                Question(
                    session_id=interview_session.id,
                    body=f"Question with sequence_order={seq_order}",
                    sequence_order=seq_order,
                    source=QUESTION_SOURCE_AI_GENERATED,
                )
            )
        db.commit()

        response = client.get(
            f"/api/v1/interviews/{interview_session.id}/questions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        actual_order = [q["sequence_order"] for q in data]
        assert actual_order == [1, 2, 3]
