"""Tests for the session report endpoints."""

import json
import uuid


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
