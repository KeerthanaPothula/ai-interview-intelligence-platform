"""Tests for the AI follow-up interviewer endpoints."""

import json
import uuid

import pytest


# ---------------------------------------------------------------------------
# Generate follow-up question — POST /interviews/{id}/follow-up-question
# ---------------------------------------------------------------------------


@pytest.fixture
def follow_up_setup(
    db,
    client,
    auth_headers,
    interview_session,
    interview_question,
    audio_response,
    transcript,
):
    """Return a dict with all IDs needed for follow-up tests."""
    return {
        "session_id": str(interview_session.id),
        "question_id": str(interview_question.id),
        "response_id": str(audio_response.id),
    }


def test_generate_follow_up_success(client, auth_headers, follow_up_setup, monkeypatch):
    """POST /follow-up-question creates a FollowUpQuestion row and returns it."""
    monkeypatch.setattr(
        "app.services.follow_up_service.generate_follow_up_question",
        lambda **_: "Can you elaborate on the specific technical challenges you faced?",
    )

    resp = client.post(
        f"/api/v1/interviews/{follow_up_setup['session_id']}/follow-up-question",
        json={
            "question_id": follow_up_setup["question_id"],
            "response_id": follow_up_setup["response_id"],
        },
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["body"] == "Can you elaborate on the specific technical challenges you faced?"
    assert data["session_id"] == follow_up_setup["session_id"]
    assert data["depth"] == 1


def test_generate_follow_up_wrong_session(client, auth_headers, follow_up_setup, monkeypatch):
    """POST with a session_id the user doesn't own returns 404."""
    monkeypatch.setattr(
        "app.services.follow_up_service.generate_follow_up_question",
        lambda **_: "Follow-up?",
    )
    fake_session_id = str(uuid.uuid4())
    resp = client.post(
        f"/api/v1/interviews/{fake_session_id}/follow-up-question",
        json={
            "question_id": follow_up_setup["question_id"],
            "response_id": follow_up_setup["response_id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_generate_follow_up_missing_transcript(
    client, auth_headers, db, interview_session, interview_question, audio_response
):
    """Returns 409 when the audio response has no transcript yet."""
    resp = client.post(
        f"/api/v1/interviews/{interview_session.id}/follow-up-question",
        json={
            "question_id": str(interview_question.id),
            "response_id": str(audio_response.id),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_generate_follow_up_requires_auth(client, follow_up_setup):
    resp = client.post(
        f"/api/v1/interviews/{follow_up_setup['session_id']}/follow-up-question",
        json={
            "question_id": follow_up_setup["question_id"],
            "response_id": follow_up_setup["response_id"],
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Conversation history — GET /interviews/{id}/conversation-history
# ---------------------------------------------------------------------------


def test_conversation_history_empty(client, auth_headers, interview_session):
    """Returns list of questions with empty follow_ups for a fresh session."""
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/conversation-history",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # interview_question fixture was not created in this test — session has no questions.
    assert data == []


def test_conversation_history_with_question(
    client, auth_headers, interview_session, interview_question
):
    """Returns the original question with an empty follow_ups list."""
    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/conversation-history",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["question_id"] == str(interview_question.id)
    assert data[0]["follow_ups"] == []


def test_conversation_history_includes_follow_ups(
    client,
    auth_headers,
    db,
    interview_session,
    interview_question,
    audio_response,
    transcript,
    monkeypatch,
):
    """After generating a follow-up, it appears in conversation history."""
    monkeypatch.setattr(
        "app.services.follow_up_service.generate_follow_up_question",
        lambda **_: "Tell me more about that.",
    )

    client.post(
        f"/api/v1/interviews/{interview_session.id}/follow-up-question",
        json={
            "question_id": str(interview_question.id),
            "response_id": str(audio_response.id),
        },
        headers=auth_headers,
    )

    resp = client.get(
        f"/api/v1/interviews/{interview_session.id}/conversation-history",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert len(data[0]["follow_ups"]) == 1
    assert data[0]["follow_ups"][0]["body"] == "Tell me more about that."


def test_conversation_history_wrong_session(client, auth_headers):
    fake_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/interviews/{fake_id}/conversation-history",
        headers=auth_headers,
    )
    assert resp.status_code == 404
