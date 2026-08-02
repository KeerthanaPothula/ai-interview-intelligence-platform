"""Tests for the admin dashboard endpoints (GET /api/v1/admin/*)."""

import uuid

from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import SESSION_STATUS_COMPLETED, SESSION_STATUS_DRAFT, InterviewSession


def _make_completed_session(db, user_id, *, job_role, final_score):
    session = InterviewSession(
        user_id=user_id,
        title="Completed Interview",
        job_role=job_role,
        job_description="A role description long enough to pass validation checks here.",
        status=SESSION_STATUS_COMPLETED,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    report = SessionReport(
        session_id=session.id,
        overall_performance="Solid performance overall.",
        final_score=final_score,
        confidence_score=80,
        communication_score=7.0,
        technical_score=7.0,
        problem_solving_score=7.0,
        readiness_level="Interview Ready",
    )
    db.add(report)
    db.commit()
    return session


def test_endpoints_require_authentication(client):
    assert client.get("/api/v1/admin/overview").status_code == 401
    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.get("/api/v1/admin/jobs").status_code == 401
    assert client.get("/api/v1/admin/activity").status_code == 401


def test_overview_with_no_data(client, auth_headers):
    response = client.get("/api/v1/admin/overview", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_users"] == 1  # the registered test user
    assert body["total_sessions"] == 0
    assert body["total_reports"] == 0
    assert body["avg_platform_score"] is None
    assert body["ai_usage"]["questions_generated"] == 0
    assert body["storage"]["audio_bytes"] == 0
    assert len(body["signups_last_30_days"]) == 30
    assert len(body["sessions_last_30_days"]) == 30


def test_overview_counts_completed_sessions_and_reports(client, auth_headers, db, registered_user):
    _make_completed_session(
        db, uuid.UUID(registered_user["id"]), job_role="Backend Engineer", final_score=8.0
    )
    _make_completed_session(
        db, uuid.UUID(registered_user["id"]), job_role="Frontend Engineer", final_score=6.0
    )

    response = client.get("/api/v1/admin/overview", headers=auth_headers)
    body = response.json()

    assert body["total_sessions"] == 2
    assert body["sessions_by_status"]["completed"] == 2
    assert body["total_reports"] == 2
    assert body["avg_platform_score"] == 7.0


def test_overview_counts_draft_sessions_separately(client, auth_headers, db, registered_user):
    draft = InterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        title="Draft session",
        job_role="Data Scientist",
        job_description="A role description long enough to pass validation checks here.",
        status=SESSION_STATUS_DRAFT,
    )
    db.add(draft)
    db.commit()

    response = client.get("/api/v1/admin/overview", headers=auth_headers)
    body = response.json()

    assert body["total_sessions"] == 1
    assert body["sessions_by_status"]["draft"] == 1
    assert body["sessions_by_status"]["completed"] == 0


def test_list_users_includes_registered_user(client, auth_headers, registered_user):
    response = client.get("/api/v1/admin/users", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 1
    user = body["items"][0]
    assert user["email"] == registered_user["email"]
    assert user["sessions_completed"] == 0
    assert user["latest_session_at"] is None


def test_list_users_search_filters_by_email(client, auth_headers, registered_user):
    match = client.get(
        "/api/v1/admin/users", params={"search": "alice"}, headers=auth_headers
    )
    assert match.json()["total"] == 1

    no_match = client.get(
        "/api/v1/admin/users", params={"search": "nobody-here"}, headers=auth_headers
    )
    assert no_match.json()["total"] == 0


def test_list_users_reflects_session_count(client, auth_headers, db, registered_user):
    _make_completed_session(
        db, uuid.UUID(registered_user["id"]), job_role="Backend Engineer", final_score=8.0
    )

    response = client.get("/api/v1/admin/users", headers=auth_headers)
    user = response.json()["items"][0]
    assert user["sessions_completed"] == 1
    assert user["latest_session_at"] is not None


def test_list_job_roles(client, auth_headers, db, registered_user):
    user_id = uuid.UUID(registered_user["id"])
    _make_completed_session(db, user_id, job_role="Backend Engineer", final_score=8.0)
    _make_completed_session(db, user_id, job_role="Backend Engineer", final_score=7.0)
    _make_completed_session(db, user_id, job_role="Frontend Engineer", final_score=6.0)

    response = client.get("/api/v1/admin/jobs", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    by_role = {row["role"]: row["session_count"] for row in body}
    assert by_role["Backend Engineer"] == 2
    assert by_role["Frontend Engineer"] == 1


def test_activity_includes_session_and_resume_events(client, auth_headers, db, registered_user):
    user_id = uuid.UUID(registered_user["id"])
    _make_completed_session(db, user_id, job_role="Backend Engineer", final_score=8.0)

    resume = ResumeDocument(
        user_id=user_id,
        filename="resume.pdf",
        file_path="fake/resume.pdf",
        extracted_text="Some resume text.",
    )
    db.add(resume)
    db.commit()

    response = client.get("/api/v1/admin/activity", headers=auth_headers)
    assert response.status_code == 200
    events = response.json()

    event_types = {e["event_type"] for e in events}
    assert "session_created" in event_types
    assert "report_generated" in event_types
    assert "resume_uploaded" in event_types
