"""Tests for GET /api/v1/recruiter/candidates."""

import uuid
from datetime import datetime, timezone

from app.models.features import SessionReport
from app.models.interview import SESSION_STATUS_COMPLETED, InterviewSession


def _make_completed_session(
    db, user_id, *, job_role, final_score, communication, technical, created_at=None
):
    session = InterviewSession(
        user_id=user_id,
        title="Completed Interview",
        job_role=job_role,
        job_description="A role description long enough to pass validation checks here.",
        status=SESSION_STATUS_COMPLETED,
        **({"created_at": created_at} if created_at is not None else {}),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    report = SessionReport(
        session_id=session.id,
        overall_performance="Solid performance overall.",
        final_score=final_score,
        confidence_score=80,
        communication_score=communication,
        technical_score=technical,
        problem_solving_score=7.0,
        readiness_level="Interview Ready",
    )
    db.add(report)
    db.commit()
    return session


def test_requires_authentication(client):
    response = client.get("/api/v1/recruiter/candidates")
    assert response.status_code == 401


def test_empty_when_no_completed_sessions(client, auth_headers):
    response = client.get("/api/v1/recruiter/candidates", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["summary"]["total_candidates"] == 0
    assert body["summary"]["avg_interview_score"] is None


def test_lists_candidate_from_completed_session(client, auth_headers, db, registered_user):
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.5,
        communication=9.0,
        technical=8.0,
    )

    response = client.get("/api/v1/recruiter/candidates", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 1
    candidate = body["items"][0]
    assert candidate["name"] == registered_user["full_name"]
    assert candidate["role"] == "Backend Engineer"
    assert candidate["interview_score"] == 85
    assert candidate["communication"] == 90
    assert candidate["technical"] == 80
    assert candidate["status"] == "shortlisted"
    assert candidate["resume_score"] is None
    assert body["summary"]["total_candidates"] == 1
    assert body["summary"]["shortlisted_count"] == 1


def test_uses_latest_completed_session_per_user(client, auth_headers, db, registered_user):
    user_id = uuid.UUID(registered_user["id"])
    _make_completed_session(
        db,
        user_id,
        job_role="Old Role",
        final_score=5.0,
        communication=5.0,
        technical=5.0,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    _make_completed_session(
        db,
        user_id,
        job_role="New Role",
        final_score=9.0,
        communication=9.0,
        technical=9.0,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    response = client.get("/api/v1/recruiter/candidates", headers=auth_headers)
    body = response.json()

    assert body["total"] == 1
    candidate = body["items"][0]
    assert candidate["role"] == "New Role"
    assert candidate["sessions_completed"] == 2


def test_search_filters_by_role(client, auth_headers, db, registered_user):
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    match = client.get(
        "/api/v1/recruiter/candidates", params={"search": "backend"}, headers=auth_headers
    )
    assert match.json()["total"] == 1

    no_match = client.get(
        "/api/v1/recruiter/candidates", params={"search": "frontend"}, headers=auth_headers
    )
    assert no_match.json()["total"] == 0


def test_status_filter(client, auth_headers, db, registered_user):
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=3.0,
        communication=3.0,
        technical=3.0,
    )

    rejected = client.get(
        "/api/v1/recruiter/candidates", params={"status": "rejected"}, headers=auth_headers
    )
    assert rejected.json()["total"] == 1

    shortlisted = client.get(
        "/api/v1/recruiter/candidates", params={"status": "shortlisted"}, headers=auth_headers
    )
    assert shortlisted.json()["total"] == 0


def test_pagination(client, auth_headers, db, registered_user):
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.get(
        "/api/v1/recruiter/candidates",
        params={"skip": 0, "limit": 1},
        headers=auth_headers,
    )
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1

    response = client.get(
        "/api/v1/recruiter/candidates",
        params={"skip": 1, "limit": 1},
        headers=auth_headers,
    )
    assert response.json()["items"] == []
