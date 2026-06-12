import io
import uuid

from app.config import get_settings
from app.models.analysis import AudioResponse, RESPONSE_STATUS_UPLOADED
from app.models.interview import (
    InterviewSession,
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


def _upload(
    client,
    auth_headers,
    session_id,
    question_id,
    *,
    file_content=None,
    filename="answer.webm",
    mime_type="audio/webm",
):
    """POST a multipart upload to /api/v1/interviews/{session_id}/responses.

    Provides a consistent interface for upload tests. file_content defaults to
    4096 bytes — above the 1024-byte minimum — so each call produces a new
    BytesIO with the cursor at position 0.
    """
    if file_content is None:
        file_content = io.BytesIO(b"x" * 4096)
    return client.post(
        f"/api/v1/interviews/{session_id}/responses",
        headers=auth_headers,
        files={"file": (filename, file_content, mime_type)},
        data={"question_id": str(question_id)},
    )


# ---------------------------------------------------------------------------
# TestAudioUpload
# ---------------------------------------------------------------------------


class TestAudioUpload:
    def test_upload_valid_file_returns_201(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        upload_dir,
        fake_audio_file,
    ):
        response = client.post(
            f"/api/v1/interviews/{interview_session.id}/responses",
            headers=auth_headers,
            files={"file": ("answer.webm", fake_audio_file, "audio/webm")},
            data={"question_id": str(interview_question.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == RESPONSE_STATUS_UPLOADED

        # Security: filesystem internals must never leak to the API caller.
        # AudioResponseResponse deliberately excludes file_path, file_size_bytes,
        # mime_type, and user_id — this assertion guards against accidental schema
        # changes that re-expose storage metadata.
        assert "file_path" not in data
        assert "upload_dir" not in data
        assert "file_size_bytes" not in data

        # No string value should look like an absolute path.
        # POSIX absolute: starts with "/"
        # Windows absolute: second char is ":" (e.g. "C:\..." or "C:/...")
        for value in data.values():
            if isinstance(value, str):
                assert not value.startswith(
                    "/"
                ), f"Absolute POSIX path leaked in response: {value!r}"
                assert not (
                    len(value) >= 3 and value[1] == ":"
                ), f"Absolute Windows path leaked in response: {value!r}"

    def test_upload_creates_db_row_with_status_uploaded(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        upload_dir,
        db,
    ):
        response = _upload(
            client, auth_headers, interview_session.id, interview_question.id
        )
        assert response.status_code == 201

        response_id = uuid.UUID(response.json()["id"])

        # Verify persistence — the row must exist in the DB with the correct status.
        # db and the client's session both use TestingSessionLocal + StaticPool
        # (same underlying connection), so committed router state is immediately
        # visible here.
        row = db.query(AudioResponse).filter(AudioResponse.id == response_id).first()
        assert row is not None
        assert row.status == RESPONSE_STATUS_UPLOADED

    def test_upload_wrong_mime_type_returns_415(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        upload_dir,
    ):
        # "text/plain" is not in _ALLOWED_MIME_TYPES — validate_upload rejects
        # it with HTTP 415 before even reading the file content.
        response = _upload(
            client,
            auth_headers,
            interview_session.id,
            interview_question.id,
            mime_type="text/plain",
        )
        assert response.status_code == 415

    def test_upload_wrong_extension_returns_415(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        upload_dir,
    ):
        # "audio/webm" passes the MIME check; ".txt" fails the subsequent
        # extension check — both must be valid for upload to proceed.
        response = _upload(
            client,
            auth_headers,
            interview_session.id,
            interview_question.id,
            filename="answer.txt",
            mime_type="audio/webm",
        )
        assert response.status_code == 415

    def test_upload_oversized_file_returns_413(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        upload_dir,
        monkeypatch,
    ):
        # Lower the size cap to 1 MB so the test runs with a 2 MB payload
        # instead of needing an actual 50 MB file.
        #
        # Why cache_clear() is called twice:
        #   get_settings() is @lru_cache. monkeypatch.setenv changes the env
        #   var but has no effect on the already-cached Settings object.
        #   cache_clear() forces re-read before the request so validate_upload
        #   sees MAX_UPLOAD_SIZE_MB=1. The second cache_clear() ensures the
        #   oversize limit does not persist into the next test via the cache
        #   (the upload_dir fixture teardown also clears it as a safety net).
        monkeypatch.setenv("MAX_UPLOAD_SIZE_MB", "1")
        get_settings.cache_clear()

        two_mb = io.BytesIO(b"x" * (2 * 1024 * 1024))
        response = _upload(
            client,
            auth_headers,
            interview_session.id,
            interview_question.id,
            file_content=two_mb,
        )

        get_settings.cache_clear()
        assert response.status_code == 413

    def test_upload_empty_file_returns_422(
        self,
        client,
        auth_headers,
        interview_session,
        interview_question,
        upload_dir,
    ):
        # 0 bytes is below the 1024-byte minimum — validate_upload raises HTTP 422.
        # MIME ("audio/webm") and extension (".webm") checks pass first; size
        # is evaluated after the file is read.
        response = _upload(
            client,
            auth_headers,
            interview_session.id,
            interview_question.id,
            file_content=io.BytesIO(b""),
        )
        assert response.status_code == 422

    def test_upload_question_belongs_to_different_session_returns_404(
        self,
        client,
        auth_headers,
        interview_session,
        upload_dir,
        registered_user,
        db,
    ):
        # Create session B — owned by the same user. The issue is not ownership
        # but that the question's session_id doesn't match the URL's session_id.
        session_b = InterviewSession(
            user_id=uuid.UUID(registered_user["id"]),
            title="Session B",
            job_role="Frontend Engineer",
            job_description="Build React interfaces for a high-traffic SaaS product.",
        )
        db.add(session_b)
        db.commit()
        db.refresh(session_b)

        question_b = Question(
            session_id=session_b.id,
            body="What is your experience with React?",
            sequence_order=1,
            source=QUESTION_SOURCE_AI_GENERATED,
        )
        db.add(question_b)
        db.commit()
        db.refresh(question_b)

        # Upload to session A's endpoint using question_b (from session B).
        # The router filters: Question.id == question_b.id AND
        #                     Question.session_id == session_A.id
        # The second condition fails → None → HTTP 404.
        response = _upload(
            client,
            auth_headers,
            interview_session.id,  # session A in URL
            question_b.id,  # question belonging to session B
        )
        # Must be 404, never 403 — session/question mismatch is not exposed.
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# TestStatusEndpoint
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    def test_status_endpoint_returns_uploaded(
        self, client, auth_headers, audio_response
    ):
        # audio_response is created directly in the DB (no real file on disk).
        # The status endpoint only reads the DB row — no filesystem access.
        response = client.get(
            f"/api/v1/responses/{audio_response.id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == RESPONSE_STATUS_UPLOADED
        # Week 3 polling contract: id and created_at must be present and stable
        # across status transitions (uploaded → processing → completed/failed).
        assert "id" in data
        assert "created_at" in data

    def test_status_other_users_response_returns_404(self, client, audio_response):
        # audio_response is owned by registered_user (User A / Alice).
        # User B's token must not be able to poll its status.
        # get_response_status filters on both response_id AND user_id in one
        # SQL query — a mismatch returns None, producing HTTP 404 (never 403).
        b_headers = _register_and_get_headers(client, _USER_B)

        response = client.get(
            f"/api/v1/responses/{audio_response.id}/status",
            headers=b_headers,
        )
        assert response.status_code == 404
