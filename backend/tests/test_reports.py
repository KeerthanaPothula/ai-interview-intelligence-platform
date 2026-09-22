"""Tests for the session report endpoints."""

import json
import uuid

from app.models.analysis import RESPONSE_STATUS_COMPLETED, Transcript
from app.models.interview import InterviewSession


_MOCK_REPORT = {
    "overall_performance": "Solid candidate with strong communication skills.",
    "final_score": 7.5,
    "confidence_score": 72,
    "communication_score": 8.0,
    "technical_score": 7.0,
    "problem_solving_score": 6.5,
    "strengths": json.dumps(["Clear articulation", "Good examples"]),
    "weaknesses": json.dumps(["Could go deeper on trade-offs"]),
    "improvement_plan": json.dumps(
        ["Practice system design", "Read more case studies"]
    ),
    "readiness_level": "Interview Ready",
    "model_used": "gemini-2.0-flash",
}


def _mock_generate(**_kwargs):
    return _MOCK_REPORT.copy()


# ---------------------------------------------------------------------------
# POST /interviews/{id}/report/generate
# ---------------------------------------------------------------------------


def test_generate_report_success(client, auth_headers, interview_session, monkeypatch):
    """Generates and persists a session report."""
    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        _mock_generate,
    )

    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["readiness_level"] == "Interview Ready"
    assert data["final_score"] == 7.5
    assert data["session_id"] == str(interview_session.id)


def test_generate_report_idempotent(
    client, auth_headers, interview_session, monkeypatch
):
    """Calling generate twice replaces the existing report."""
    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        _mock_generate,
    )

    resp1 = client.post(
        f"/api/v1/interviews/{interview_session.id}/report/generate",
        headers=auth_headers,
    )
    assert resp1.status_code == 201

    modified = _MOCK_REPORT.copy()
    modified["readiness_level"] = "Strong Candidate"
    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        lambda **_: modified,
    )

    resp2 = client.post(
        f"/api/v1/interviews/{interview_session.id}/report/generate",
        headers=auth_headers,
    )
    assert resp2.status_code == 201
    assert resp2.json()["readiness_level"] == "Strong Candidate"


def test_generate_report_wrong_session(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        _mock_generate,
    )
    fake_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/interviews/{fake_id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_generate_report_requires_auth(client, interview_session):
    resp = client.post(f"/api/v1/interviews/{interview_session.id}/report/generate")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /interviews/{id}/report
# ---------------------------------------------------------------------------


def test_get_report_not_generated(client, auth_headers, interview_session):
    """Returns 404 before report has been generated."""
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/report",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_get_report_after_generate(
    client, auth_headers, interview_session, monkeypatch
):
    """GET /report returns the previously generated report."""
    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        _mock_generate,
    )
    client.post(
        f"/api/v1/interviews/{interview_session.id}/report/generate",
        headers=auth_headers,
    )

    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/report",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["readiness_level"] == "Interview Ready"
    assert data["confidence_score"] == 72


def test_get_report_wrong_session(client, auth_headers):
    fake_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/interviews/{fake_id}/report",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_get_report_requires_auth(client, interview_session):
    resp = client.get(f"/api/v1/interviews/{interview_session.id}/report")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Report generation for a mirrored live-interview session
# ---------------------------------------------------------------------------


def _complete_live_interview_and_get_mirror_id(client, auth_headers, db, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        lambda job_role, job_description: "Tell me about a challenging project.",
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        lambda **kwargs: ("What would you do differently?", 2),
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        lambda **kwargs: "Solid overall performance.",
    )

    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Data Engineer",
            "job_description": "Python data pipeline engineering role.",
            "max_turns": 3,
        },
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "I rebuilt our ETL pipeline to cut latency by half."},
        headers=auth_headers,
    )

    client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)

    mirrored = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == uuid.UUID(session_id))
        .one()
    )
    return str(mirrored.id)


def test_generate_report_for_live_session_uses_conversation_turns(
    client, auth_headers, db, monkeypatch
):
    """The live-interview report branch reads Q&A from ConversationTurn text,
    never from AudioResponse/Transcript/InterviewAnalysis (there are none),
    and passes no per-answer scores through to report_service."""
    mirrored_id = _complete_live_interview_and_get_mirror_id(
        client, auth_headers, db, monkeypatch
    )

    captured = {}

    def _capturing_generate(**kwargs):
        captured.update(kwargs)
        return _MOCK_REPORT.copy()

    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        _capturing_generate,
    )

    resp = client.post(
        f"/api/v1/interviews/{mirrored_id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text

    assert captured["analyses"] == []
    assert captured["voice_analytics"] == []
    questions = [qt["question"] for qt in captured["questions_and_transcripts"]]
    transcripts = [qt["transcript"] for qt in captured["questions_and_transcripts"]]
    assert "Tell me about a challenging project." in questions
    assert "I rebuilt our ETL pipeline to cut latency by half." in transcripts


def test_live_session_report_does_not_invent_numeric_scores(
    client, auth_headers, db, monkeypatch
):
    """With no analyses/voice_analytics, report_service's own averaging
    (_safe_mean on an empty list) yields None — this asserts the endpoint
    surfaces that None rather than a fabricated number, using the real
    (unmocked) report_service.generate_session_report."""
    mirrored_id = _complete_live_interview_and_get_mirror_id(
        client, auth_headers, db, monkeypatch
    )

    # Only the Gemini call itself is mocked — report_service's own score
    # aggregation logic runs for real.
    class _FakeResponse:
        text = (
            '{"overall_performance": "Did fine.", "strengths": ["Clear communicator"], '
            '"weaknesses": [], "improvement_plan": [], "readiness_level": "Developing"}'
        )

    class _FakeModels:
        def generate_content(self, model, contents):
            return _FakeResponse()

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(
        "app.services.report_service._get_client", lambda: _FakeClient()
    )

    resp = client.post(
        f"/api/v1/interviews/{mirrored_id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["final_score"] is None
    assert data["communication_score"] is None
    assert data["technical_score"] is None
    assert data["problem_solving_score"] is None
    assert data["confidence_score"] is None
    assert data["readiness_level"] == "Developing"


def test_upload_flow_report_generation_unchanged(
    client, auth_headers, interview_session, interview_question, audio_response, db,
    monkeypatch,
):
    """Regression check: a normal (non-live) session with a real Question +
    completed AudioResponse still goes through the original code path
    (untouched by the live-interview branch) and produces a report."""
    audio_response.status = RESPONSE_STATUS_COMPLETED
    db.add(
        Transcript(
            audio_response_id=audio_response.id,
            text="I led the migration to a microservices architecture.",
            word_count=8,
        )
    )
    db.commit()

    captured = {}

    def _capturing_generate(**kwargs):
        captured.update(kwargs)
        return _MOCK_REPORT.copy()

    monkeypatch.setattr(
        "app.services.report_service.generate_session_report",
        _capturing_generate,
    )

    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert len(captured["questions_and_transcripts"]) == 1
    assert (
        captured["questions_and_transcripts"][0]["transcript"]
        == "I led the migration to a microservices architecture."
    )
