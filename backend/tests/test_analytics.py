"""Tests for the analytics dashboard endpoints."""

import uuid


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/overview
# ---------------------------------------------------------------------------


def test_analytics_overview_no_data(client, auth_headers):
    """Returns zeroed overview when user has no sessions."""
    resp = client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 0
    assert data["completed_sessions"] == 0
    assert data["total_responses_analyzed"] == 0
    assert data["average_overall_score"] is None
    assert data["strongest_skill"] is None
    assert data["weakest_skill"] is None
    assert data["improvement_score"] is None


def test_analytics_overview_with_analysis(
    client, auth_headers, interview_session, interview_analysis
):
    """Returns aggregated stats when at least one analysis exists."""
    resp = client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 1
    assert data["total_responses_analyzed"] == 1
    # interview_analysis has overall_score=7.5
    assert data["average_overall_score"] == 7.5
    assert data["strongest_skill"] is not None
    assert data["weakest_skill"] is not None


def test_analytics_overview_requires_auth(client):
    resp = client.get("/api/v1/analytics/overview")
    assert resp.status_code == 401


def test_analytics_overview_scoped_to_user(
    client, auth_headers, registered_user, interview_session, interview_analysis
):
    """A second user sees zero stats even though data exists for the first user."""
    # Register a second user and get their token.
    client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "securepassword1", "full_name": "Bob"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "bob@example.com", "password": "securepassword1"},
    )
    bob_token = login_resp.json()["access_token"]
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    resp = client.get("/api/v1/analytics/overview", headers=bob_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sessions"] == 0
    assert data["total_responses_analyzed"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/trends
# ---------------------------------------------------------------------------


def test_analytics_trends_empty(client, auth_headers):
    resp = client.get("/api/v1/analytics/trends", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_analytics_trends_with_session(
    client, auth_headers, interview_session, interview_analysis
):
    """Returns one entry per session."""
    resp = client.get("/api/v1/analytics/trends", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    entry = data[0]
    assert entry["session_id"] == str(interview_session.id)
    assert entry["session_title"] == interview_session.title
    assert entry["average_overall_score"] == 7.5
    assert entry["average_communication_score"] == 8.0
    assert entry["average_technical_score"] == 7.0
    assert entry["average_problem_solving_score"] == 6.5


def test_analytics_trends_requires_auth(client):
    resp = client.get("/api/v1/analytics/trends")
    assert resp.status_code == 401
