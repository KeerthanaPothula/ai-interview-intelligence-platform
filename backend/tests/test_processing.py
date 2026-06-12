import json
import uuid
from decimal import Decimal

from fastapi import HTTPException

from app.config import get_settings
from app.models.analysis import (
    AudioResponse,
    InterviewAnalysis,
    RESPONSE_STATUS_COMPLETED,
    RESPONSE_STATUS_FAILED,
    RESPONSE_STATUS_PROCESSING,
    RESPONSE_STATUS_UPLOADED,
    Transcript,
)
from app.models.interview import SESSION_STATUS_COMPLETED
from app.services import processing_service

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


def _make_response(db, session, question, user, status, *, error_message=None):
    """Create and return an AudioResponse with an arbitrary status.

    Mirrors the audio_response fixture's shape, but lets Group A create
    several rows (one per status) against the same session/question.
    """
    response_id = uuid.uuid4()
    response = AudioResponse(
        id=response_id,
        session_id=session.id,
        question_id=question.id,
        user_id=uuid.UUID(user["id"]),
        file_path=f"{session.id}/{response_id}.webm",
        file_size_bytes=4096,
        mime_type="audio/webm",
        status=status,
        error_message=error_message,
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


# ---------------------------------------------------------------------------
# Group A — Startup Recovery
# ---------------------------------------------------------------------------


class TestRecoverStuckJobs:
    def test_recover_stuck_jobs_marks_processing_failed(
        self, db, interview_session, interview_question, registered_user
    ):
        uploaded = _make_response(
            db, interview_session, interview_question, registered_user,
            RESPONSE_STATUS_UPLOADED,
        )
        processing = _make_response(
            db, interview_session, interview_question, registered_user,
            RESPONSE_STATUS_PROCESSING,
        )
        failed = _make_response(
            db, interview_session, interview_question, registered_user,
            RESPONSE_STATUS_FAILED,
            error_message="Previous attempt: timed out",
        )
        completed = _make_response(
            db, interview_session, interview_question, registered_user,
            RESPONSE_STATUS_COMPLETED,
        )

        recovered_count = processing_service.recover_stuck_jobs(db)

        assert recovered_count == 1

        db.refresh(uploaded)
        db.refresh(processing)
        db.refresh(failed)
        db.refresh(completed)

        # Only the 'processing' row is touched.
        assert processing.status == RESPONSE_STATUS_FAILED
        assert processing.error_message == "Server restart interrupted processing"

        # Every other row is left exactly as it was.
        assert uploaded.status == RESPONSE_STATUS_UPLOADED
        assert uploaded.error_message is None

        assert failed.status == RESPONSE_STATUS_FAILED
        assert failed.error_message == "Previous attempt: timed out"

        assert completed.status == RESPONSE_STATUS_COMPLETED
        assert completed.error_message is None


# ---------------------------------------------------------------------------
# Group B — Claim Logic
# ---------------------------------------------------------------------------


class TestClaimResponse:
    def test_claim_uploaded_returns_true(self, db, audio_response):
        result = processing_service.claim_response(db, audio_response.id)
        assert result is True

        db.commit()
        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_PROCESSING

    def test_claim_failed_returns_true(self, db, audio_response):
        db.query(AudioResponse).filter(AudioResponse.id == audio_response.id).update(
            {"status": RESPONSE_STATUS_FAILED}, synchronize_session=False
        )
        db.commit()

        result = processing_service.claim_response(db, audio_response.id)
        assert result is True

        db.commit()
        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_PROCESSING

    def test_claim_processing_returns_false(self, db, audio_response):
        db.query(AudioResponse).filter(AudioResponse.id == audio_response.id).update(
            {"status": RESPONSE_STATUS_PROCESSING}, synchronize_session=False
        )
        db.commit()

        result = processing_service.claim_response(db, audio_response.id)
        assert result is False

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_PROCESSING

    def test_claim_completed_returns_false(self, db, audio_response):
        db.query(AudioResponse).filter(AudioResponse.id == audio_response.id).update(
            {"status": RESPONSE_STATUS_COMPLETED}, synchronize_session=False
        )
        db.commit()

        result = processing_service.claim_response(db, audio_response.id)
        assert result is False

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_COMPLETED


# ---------------------------------------------------------------------------
# Group C — Successful Processing Pipeline
# ---------------------------------------------------------------------------


class TestProcessResponseSuccess:
    def test_process_response_creates_transcript_and_analysis(
        self,
        db,
        processing_enabled,
        mock_transcription,
        mock_evaluation,
        audio_response,
    ):
        processing_service.process_response(audio_response.id)

        transcript = (
            db.query(Transcript)
            .filter(Transcript.audio_response_id == audio_response.id)
            .first()
        )
        assert transcript is not None
        assert transcript.text == mock_transcription["text"]
        assert transcript.language == mock_transcription["language"]
        assert transcript.word_count == mock_transcription["word_count"]

        analysis = (
            db.query(InterviewAnalysis)
            .filter(InterviewAnalysis.audio_response_id == audio_response.id)
            .first()
        )
        assert analysis is not None
        assert analysis.transcript_id == transcript.id
        assert analysis.overall_score == Decimal("7.5")
        assert analysis.model_used == mock_evaluation["model_used"]

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_COMPLETED
        assert audio_response.processing_completed_at is not None

    def test_process_response_marks_session_completed(
        self,
        db,
        processing_enabled,
        mock_transcription,
        mock_evaluation,
        audio_response,
        interview_session,
    ):
        # audio_response is the only response in interview_session.
        processing_service.process_response(audio_response.id)

        db.refresh(interview_session)
        assert interview_session.status == SESSION_STATUS_COMPLETED


# ---------------------------------------------------------------------------
# Group D — Failure Paths
# ---------------------------------------------------------------------------


class TestProcessResponseFailures:
    def test_process_response_transcription_failure(
        self, db, audio_response, monkeypatch
    ):
        def _raise_transcription_error(file_path):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "app.services.transcription_service.transcribe_audio",
            _raise_transcription_error,
        )

        processing_service.process_response(audio_response.id)

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_FAILED
        assert "boom" in audio_response.error_message

    def test_process_response_evaluation_failure(
        self, db, mock_transcription, audio_response, monkeypatch
    ):
        def _raise_evaluation_error(**kwargs):
            raise HTTPException(
                status_code=502, detail="Interview evaluation service is currently unavailable."
            )

        monkeypatch.setattr(
            "app.services.evaluation_service.generate_evaluation",
            _raise_evaluation_error,
        )

        processing_service.process_response(audio_response.id)

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_FAILED
        assert audio_response.error_message is not None

        # Transaction 2 already committed before evaluation ran — the
        # transcript survives the later failure.
        transcript = (
            db.query(Transcript)
            .filter(Transcript.audio_response_id == audio_response.id)
            .first()
        )
        assert transcript is not None

    def test_process_response_missing_response_noop(self, db):
        # No AudioResponse row exists for this id. claim_response's UPDATE
        # matches zero rows, _claim_and_load_context returns None, and
        # process_response returns early without raising.
        processing_service.process_response(uuid.uuid4())


# ---------------------------------------------------------------------------
# Group D.1 — Retry Idempotency
# ---------------------------------------------------------------------------


class TestRetryIdempotency:
    def test_retry_after_evaluation_failure_reuses_transcript(
        self,
        db,
        processing_enabled,
        mock_transcription,
        mock_evaluation,
        audio_response,
        monkeypatch,
    ):
        # First attempt: transcription succeeds (Transaction 2 commits a
        # Transcript row), but evaluation fails -> status='failed'.
        def _raise_evaluation_error(**kwargs):
            raise HTTPException(
                status_code=502,
                detail="Interview evaluation service is currently unavailable.",
            )

        monkeypatch.setattr(
            "app.services.evaluation_service.generate_evaluation",
            _raise_evaluation_error,
        )

        processing_service.process_response(audio_response.id)

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_FAILED

        transcripts = (
            db.query(Transcript)
            .filter(Transcript.audio_response_id == audio_response.id)
            .all()
        )
        assert len(transcripts) == 1
        first_transcript_id = transcripts[0].id

        # Retry: evaluation now succeeds. The existing Transcript must be
        # reused, not duplicated.
        monkeypatch.setattr(
            "app.services.evaluation_service.generate_evaluation",
            lambda **kwargs: mock_evaluation,
        )

        processing_service.process_response(audio_response.id)

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_COMPLETED

        transcripts = (
            db.query(Transcript)
            .filter(Transcript.audio_response_id == audio_response.id)
            .all()
        )
        assert len(transcripts) == 1
        assert transcripts[0].id == first_transcript_id

        analyses = (
            db.query(InterviewAnalysis)
            .filter(InterviewAnalysis.audio_response_id == audio_response.id)
            .all()
        )
        assert len(analyses) == 1
        assert analyses[0].transcript_id == first_transcript_id

    def test_retry_does_not_call_transcribe_again(
        self,
        db,
        processing_enabled,
        mock_transcription,
        mock_evaluation,
        audio_response,
        monkeypatch,
    ):
        # First attempt: transcription succeeds, evaluation fails ->
        # status='failed' with a Transcript already committed.
        def _raise_evaluation_error(**kwargs):
            raise HTTPException(
                status_code=502,
                detail="Interview evaluation service is currently unavailable.",
            )

        monkeypatch.setattr(
            "app.services.evaluation_service.generate_evaluation",
            _raise_evaluation_error,
        )

        processing_service.process_response(audio_response.id)

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_FAILED

        # Retry: transcribe_audio must NOT be called again. If it were, this
        # counter would be incremented; the lambda below also keeps the
        # pipeline from crashing in case it is (unexpectedly) invoked.
        call_count = {"n": 0}

        def _track_transcribe(file_path):
            call_count["n"] += 1
            return mock_transcription

        monkeypatch.setattr(
            "app.services.transcription_service.transcribe_audio",
            _track_transcribe,
        )
        monkeypatch.setattr(
            "app.services.evaluation_service.generate_evaluation",
            lambda **kwargs: mock_evaluation,
        )

        processing_service.process_response(audio_response.id)

        assert call_count["n"] == 0

        db.refresh(audio_response)
        assert audio_response.status == RESPONSE_STATUS_COMPLETED


# ---------------------------------------------------------------------------
# Group E — Router Tests: POST /responses/{response_id}/process
# ---------------------------------------------------------------------------


class TestTriggerProcessingEndpoint:
    def test_trigger_processing_disabled_returns_503(
        self, client, auth_headers, audio_response
    ):
        # Default test environment: ENABLE_AUDIO_PROCESSING=false (conftest).
        response = client.post(
            f"/api/v1/responses/{audio_response.id}/process",
            headers=auth_headers,
            json={"response_id": str(audio_response.id)},
        )
        assert response.status_code == 503

    def test_trigger_processing_enqueues(
        self, client, auth_headers, audio_response, processing_enabled, monkeypatch
    ):
        captured: list[uuid.UUID] = []

        def _fake_process_response(response_id):
            captured.append(response_id)

        monkeypatch.setattr(
            "app.services.processing_service.process_response",
            _fake_process_response,
        )

        response = client.post(
            f"/api/v1/responses/{audio_response.id}/process",
            headers=auth_headers,
            json={"response_id": str(audio_response.id)},
        )

        # trigger_processing returns 202 Accepted (File 09).
        assert response.status_code == 202
        assert captured == [audio_response.id]

        data = response.json()
        assert data["response_id"] == str(audio_response.id)

    def test_trigger_processing_other_user_returns_404(self, client, audio_response):
        # audio_response is owned by registered_user (User A / Alice).
        # User B's token must not be able to trigger processing on it.
        b_headers = _register_and_get_headers(client, _USER_B)

        response = client.post(
            f"/api/v1/responses/{audio_response.id}/process",
            headers=b_headers,
            json={"response_id": str(audio_response.id)},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Group E — Router Tests: GET /responses/{response_id}/processing-status
# ---------------------------------------------------------------------------


class TestProcessingStatusEndpoint:
    def test_processing_status_returns_completed(
        self, client, auth_headers, db, audio_response, transcript, interview_analysis
    ):
        db.query(AudioResponse).filter(AudioResponse.id == audio_response.id).update(
            {"status": RESPONSE_STATUS_COMPLETED}, synchronize_session=False
        )
        db.commit()

        response = client.get(
            f"/api/v1/responses/{audio_response.id}/processing-status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == RESPONSE_STATUS_COMPLETED
        assert data["transcript_id"] == str(transcript.id)
        assert data["analysis_id"] == str(interview_analysis.id)

    def test_processing_status_other_user_returns_404(self, client, audio_response):
        b_headers = _register_and_get_headers(client, _USER_B)

        response = client.get(
            f"/api/v1/responses/{audio_response.id}/processing-status",
            headers=b_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Group F — Transcript Truncation
# ---------------------------------------------------------------------------


class TestTranscriptTruncation:
    def test_transcript_truncation_before_evaluation(
        self, db, processing_enabled, audio_response, monkeypatch
    ):
        long_text = "word " * 30  # 150 chars, > 100
        assert len(long_text) > 100

        def _fake_transcribe_audio(file_path):
            return {
                "text": long_text,
                "language": "en",
                "duration_seconds": 60,
                "word_count": len(long_text.split()),
            }

        captured: dict = {}

        def _fake_generate_evaluation(**kwargs):
            captured["transcript_text"] = kwargs["transcript_text"]
            return {
                "overall_score": 7.5,
                "communication_score": 8.0,
                "technical_score": 7.0,
                "problem_solving_score": 6.5,
                "confidence_score": 8.5,
                "strengths": json.dumps(["Clear structure"]),
                "weaknesses": json.dumps(["Could improve depth"]),
                "detailed_feedback": "Solid response overall.",
                "model_used": "gemini-2.0-flash",
            }

        monkeypatch.setattr(
            "app.services.transcription_service.transcribe_audio",
            _fake_transcribe_audio,
        )
        monkeypatch.setattr(
            "app.services.evaluation_service.generate_evaluation",
            _fake_generate_evaluation,
        )

        # Cache-clearing order matches the upload_dir fixture: clear now so
        # process_response's get_settings() call sees MAX_TRANSCRIPT_CHARS=10,
        # then clear again after assertions but before monkeypatch's teardown
        # restores the env var, so the next test's first get_settings() call
        # re-reads the restored (default) value.
        monkeypatch.setenv("MAX_TRANSCRIPT_CHARS", "10")
        get_settings.cache_clear()

        processing_service.process_response(audio_response.id)

        assert len(captured["transcript_text"]) == 10
        assert captured["transcript_text"] == long_text[:10]

        transcript = (
            db.query(Transcript)
            .filter(Transcript.audio_response_id == audio_response.id)
            .first()
        )
        assert transcript is not None
        assert transcript.text == long_text
        assert len(transcript.text) == len(long_text)

        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Group G — Router Tests: GET /responses/{response_id}/transcript
# ---------------------------------------------------------------------------


class TestGetTranscriptEndpoint:
    def test_get_transcript_returns_200(
        self, client, auth_headers, audio_response, transcript
    ):
        response = client.get(
            f"/api/v1/responses/{audio_response.id}/transcript",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(transcript.id)
        assert data["audio_response_id"] == str(audio_response.id)
        assert data["text"] == transcript.text
        assert data["language"] == transcript.language
        assert data["word_count"] == transcript.word_count

    def test_get_transcript_missing_returns_404(
        self, client, auth_headers, audio_response
    ):
        # audio_response exists but no Transcript row has been created yet.
        response = client.get(
            f"/api/v1/responses/{audio_response.id}/transcript",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_transcript_other_user_returns_404(
        self, client, audio_response, transcript
    ):
        # transcript belongs to a response owned by registered_user (Alice).
        b_headers = _register_and_get_headers(client, _USER_B)

        response = client.get(
            f"/api/v1/responses/{audio_response.id}/transcript",
            headers=b_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Group H — Router Tests: GET /responses/{response_id}/analysis
# ---------------------------------------------------------------------------


class TestGetAnalysisEndpoint:
    def test_get_analysis_returns_200(
        self, client, auth_headers, audio_response, interview_analysis
    ):
        response = client.get(
            f"/api/v1/responses/{audio_response.id}/analysis",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(interview_analysis.id)
        assert data["audio_response_id"] == str(audio_response.id)
        assert data["transcript_id"] == str(interview_analysis.transcript_id)
        assert data["overall_score"] == str(interview_analysis.overall_score)
        assert data["model_used"] == interview_analysis.model_used

    def test_get_analysis_missing_returns_404(
        self, client, auth_headers, audio_response
    ):
        # audio_response exists but no InterviewAnalysis row has been created yet.
        response = client.get(
            f"/api/v1/responses/{audio_response.id}/analysis",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_analysis_other_user_returns_404(
        self, client, audio_response, interview_analysis
    ):
        # interview_analysis belongs to a response owned by registered_user (Alice).
        b_headers = _register_and_get_headers(client, _USER_B)

        response = client.get(
            f"/api/v1/responses/{audio_response.id}/analysis",
            headers=b_headers,
        )
        assert response.status_code == 404
