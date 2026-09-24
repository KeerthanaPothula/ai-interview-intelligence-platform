"""Tests for the session report endpoints."""

import json
import uuid

from app.models.analysis import RESPONSE_STATUS_COMPLETED, Transcript
from app.models.interview import InterviewSession
from tests.test_analytics_live import _live


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
    # The submitted response_text below now triggers best-effort per-turn
    # scoring (interview_service.score_and_store_conversation_turn) —
    # mocked so this test never makes a real network call.
    monkeypatch.setattr(
        "app.services.evaluation_service.generate_evaluation",
        lambda **kwargs: {
            "overall_score": 7.0,
            "communication_score": 7.0,
            "technical_score": 7.0,
            "problem_solving_score": 7.0,
            "confidence_score": 7.0,
            "strengths": "[]",
            "weaknesses": "[]",
            "detailed_feedback": "Fine.",
            "model_used": "gemini-test-model",
        },
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
    and passes the genuine ConversationTurnAnalysis scores to report_service
    (one answered turn scored 7.0; the unanswered final turn adds nothing)."""
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

    assert captured["analyses"] == [
        {
            "overall_score": 7.0,
            "communication_score": 7.0,
            "technical_score": 7.0,
            "problem_solving_score": 7.0,
        }
    ]
    assert captured["voice_analytics"] == []
    questions = [qt["question"] for qt in captured["questions_and_transcripts"]]
    transcripts = [qt["transcript"] for qt in captured["questions_and_transcripts"]]
    assert "Tell me about a challenging project." in questions
    assert "I rebuilt our ETL pipeline to cut latency by half." in transcripts


class _FakeGemini:
    """Mocks only the Gemini call, so report_service's real score averaging
    runs; records the prompt it was sent."""

    def __init__(self):
        self.prompts = []
        outer = self

        class _Models:
            def generate_content(self, model, contents):
                outer.prompts.append(contents)

                class _R:
                    text = (
                        '{"overall_performance": "Did fine.", '
                        '"strengths": ["Clear communicator"], "weaknesses": [], '
                        '"improvement_plan": [], "readiness_level": "Developing"}'
                    )

                return _R()

        self.models = _Models()


def test_live_session_report_uses_genuine_scores(client, auth_headers, db, monkeypatch):
    """End to end through the live endpoints and the real report_service:
    the report carries the answer's genuine score, and confidence_score (a
    voice metric) stays None because live interviews have no audio."""
    mirrored_id = _complete_live_interview_and_get_mirror_id(
        client, auth_headers, db, monkeypatch
    )
    gemini = _FakeGemini()
    monkeypatch.setattr("app.services.report_service._get_client", lambda: gemini)

    resp = client.post(
        f"/api/v1/interviews/{mirrored_id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["final_score"] == 7.0
    assert data["communication_score"] == 7.0
    assert data["technical_score"] == 7.0
    assert data["problem_solving_score"] == 7.0
    assert data["confidence_score"] is None
    assert "Overall: 7.0/10" in gemini.prompts[0]
    assert "None/10" not in gemini.prompts[0]


def test_live_report_averages_scored_answers_and_skips_unscored(
    client, auth_headers, db, registered_user, monkeypatch
):
    mirrored = _live(
        db,
        registered_user["id"],
        [(6.0, 9.0, 5.0, 6.0, 7.0), (9.0, 8.0, 6.0, 7.0, 8.0), None],
    )
    gemini = _FakeGemini()
    monkeypatch.setattr("app.services.report_service._get_client", lambda: gemini)

    resp = client.post(
        f"/api/v1/interviews/{mirrored.id}/report/generate", headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["final_score"] == 7.5
    assert data["communication_score"] == 8.5
    assert data["technical_score"] == 5.5
    assert data["problem_solving_score"] == 6.5
    assert data["confidence_score"] is None
    assert (
        "Overall: 7.5/10, Communication: 8.5/10, Technical: 5.5/10, "
        "Problem Solving: 6.5/10" in gemini.prompts[0]
    )


def test_live_report_with_no_scored_answers_does_not_invent_scores(
    client, auth_headers, db, registered_user, monkeypatch
):
    mirrored = _live(db, registered_user["id"], [None, None])
    monkeypatch.setattr(
        "app.services.report_service._get_client", lambda: _FakeGemini()
    )

    resp = client.post(
        f"/api/v1/interviews/{mirrored.id}/report/generate", headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    for key in (
        "final_score",
        "communication_score",
        "technical_score",
        "problem_solving_score",
        "confidence_score",
    ):
        assert data[key] is None, key


def test_upload_flow_report_scores_unchanged(
    client, auth_headers, interview_session, interview_analysis, monkeypatch
):
    """The upload branch still averages InterviewAnalysis rows (fixture:
    7.5 / 8.0 / 7.0 / 6.5) exactly as before."""
    captured = {}

    def _capturing_generate(**kwargs):
        captured.update(kwargs)
        return _MOCK_REPORT.copy()

    monkeypatch.setattr(
        "app.services.report_service.generate_session_report", _capturing_generate
    )

    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/report/generate",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    assert captured["analyses"] == [
        {
            "overall_score": 7.5,
            "communication_score": 8.0,
            "technical_score": 7.0,
            "problem_solving_score": 6.5,
        }
    ]
    assert captured["voice_analytics"] == []


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
