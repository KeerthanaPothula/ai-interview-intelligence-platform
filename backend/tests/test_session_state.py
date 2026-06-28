import io

from app.models.interview import SESSION_STATUS_DRAFT, SESSION_STATUS_IN_PROGRESS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upload(client, auth_headers, session_id, question_id):
    """POST a minimal valid audio upload to /api/v1/interviews/{session_id}/responses."""
    return client.post(
        f"/api/v1/interviews/{session_id}/responses",
        headers=auth_headers,
        files={
            "file": (
                "answer.webm",
                io.BytesIO(b"\x1a\x45\xdf\xa3" + b"x" * 4092),
                "audio/webm",
            )
        },
        data={"question_id": str(question_id)},
    )


# ---------------------------------------------------------------------------
# TestSessionStateTransitions
#
# Covers Phase 5: a session moves draft -> in_progress on its first
# AudioResponse, stays in_progress on subsequent uploads, and draft-only
# routes (question regeneration, session update) reject once the session
# has left draft — using the existing HTTP 409 contract.
# ---------------------------------------------------------------------------


class TestSessionStateTransitions:
    def test_first_response_moves_session_to_in_progress(
        self,
        client,
        auth_headers,
        db,
        interview_session,
        interview_question,
        upload_dir,
    ):
        assert interview_session.status == SESSION_STATUS_DRAFT

        response = _upload(
            client, auth_headers, interview_session.id, interview_question.id
        )
        assert response.status_code == 201

        db.refresh(interview_session)
        assert interview_session.status == SESSION_STATUS_IN_PROGRESS

    def test_second_response_does_not_change_state(
        self,
        client,
        auth_headers,
        db,
        interview_session,
        interview_question,
        upload_dir,
    ):
        first = _upload(
            client, auth_headers, interview_session.id, interview_question.id
        )
        assert first.status_code == 201

        db.refresh(interview_session)
        assert interview_session.status == SESSION_STATUS_IN_PROGRESS

        second = _upload(
            client, auth_headers, interview_session.id, interview_question.id
        )
        assert second.status_code == 201

        db.refresh(interview_session)
        assert interview_session.status == SESSION_STATUS_IN_PROGRESS

    def test_regenerate_questions_rejected_after_progress(
        self,
        client,
        auth_headers,
        db,
        interview_session,
        interview_question,
        upload_dir,
    ):
        upload = _upload(
            client, auth_headers, interview_session.id, interview_question.id
        )
        assert upload.status_code == 201

        db.refresh(interview_session)
        assert interview_session.status == SESSION_STATUS_IN_PROGRESS

        response = client.post(
            f"/api/v1/interviews/{interview_session.id}/questions/generate",
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_update_session_rejected_after_progress(
        self,
        client,
        auth_headers,
        db,
        interview_session,
        interview_question,
        upload_dir,
    ):
        upload = _upload(
            client, auth_headers, interview_session.id, interview_question.id
        )
        assert upload.status_code == 201

        db.refresh(interview_session)
        assert interview_session.status == SESSION_STATUS_IN_PROGRESS

        response = client.patch(
            f"/api/v1/interviews/{interview_session.id}",
            json={"title": "Should Be Rejected"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_existing_draft_behavior_still_works(
        self, client, auth_headers, db, interview_session
    ):
        # No response has been uploaded — session remains in draft, and
        # draft-only operations (e.g. session update) continue to succeed.
        assert interview_session.status == SESSION_STATUS_DRAFT

        response = client.patch(
            f"/api/v1/interviews/{interview_session.id}",
            json={"title": "Still Draft"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Still Draft"
