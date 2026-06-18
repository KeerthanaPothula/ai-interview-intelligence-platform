"""Tests for live conversational AI interviewer endpoints."""

import uuid


_FIRST_Q = "Tell me about your most challenging project."
_NEXT_Q = "Can you elaborate on the technical decisions you made?"
_SUMMARY = "Strong performance overall with good technical depth."


def _mock_opening(job_role, job_description):
    return _FIRST_Q


def _mock_follow_up(**kwargs):
    return _NEXT_Q, 2


def _mock_summary(**kwargs):
    return _SUMMARY


# ---------------------------------------------------------------------------
# POST /api/v1/live-interviews/
# ---------------------------------------------------------------------------


def test_start_live_interview_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Software Engineer", "job_description": "Python backend role with FastAPI", "max_turns": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "active"
    assert data["current_turn"] == 1
    assert data["max_turns"] == 3
    assert data["current_question"]["question_text"] == _FIRST_Q
    assert data["current_question"]["difficulty_level"] == 1


def test_start_live_interview_requires_auth(client):
    resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "A backend engineering role.", "max_turns": 3},
    )
    assert resp.status_code == 401


def test_start_live_interview_validation(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    # job_description too short
    resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "short", "max_turns": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/live-interviews/{id}/next-question
# ---------------------------------------------------------------------------


def test_next_question_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )

    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "Python backend engineering role.", "max_turns": 3},
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/next-question",
        json={"response_text": "I built a distributed caching system at scale."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["current_turn"] == 2
    assert data["current_question"]["question_text"] == _NEXT_Q
    assert data["current_question"]["difficulty_level"] == 2


def test_next_question_wrong_session(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_follow_up_question",
        _mock_follow_up,
    )
    resp = client.post(
        f"/api/v1/live-interviews/{uuid.uuid4()}/next-question",
        json={"response_text": "answer"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_next_question_requires_auth(client):
    resp = client.post(
        f"/api/v1/live-interviews/{uuid.uuid4()}/next-question",
        json={"response_text": "answer"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/live-interviews/{id}/conversation
# ---------------------------------------------------------------------------


def test_get_conversation_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "Python backend engineering role.", "max_turns": 3},
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.get(
        f"/api/v1/live-interviews/{session_id}/conversation",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["turns"]) == 1
    assert data["turns"][0]["question_text"] == _FIRST_Q


def test_get_conversation_wrong_session(client, auth_headers):
    resp = client.get(
        f"/api/v1/live-interviews/{uuid.uuid4()}/conversation",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/live-interviews/{id}/end
# ---------------------------------------------------------------------------


def test_end_interview_success(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "Python backend engineering role.", "max_turns": 3},
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    resp = client.post(
        f"/api/v1/live-interviews/{session_id}/end",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert data["summary"] == _SUMMARY
    assert data["total_turns"] == 1


def test_end_interview_double_end(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_opening_question",
        _mock_opening,
    )
    monkeypatch.setattr(
        "app.services.interview_conversation_service.generate_interview_summary",
        _mock_summary,
    )
    start_resp = client.post(
        "/api/v1/live-interviews/",
        json={"job_role": "Engineer", "job_description": "Python backend engineering role.", "max_turns": 3},
        headers=auth_headers,
    )
    session_id = start_resp.json()["id"]

    client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)
    resp2 = client.post(f"/api/v1/live-interviews/{session_id}/end", headers=auth_headers)
    assert resp2.status_code == 409


def test_end_interview_requires_auth(client):
    resp = client.post(f"/api/v1/live-interviews/{uuid.uuid4()}/end")
    assert resp.status_code == 401
