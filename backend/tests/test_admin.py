"""Tests for the admin dashboard endpoints (GET/POST/PATCH /api/v1/admin/*)."""

import uuid

from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import (
    SESSION_STATUS_COMPLETED,
    SESSION_STATUS_DRAFT,
    InterviewSession,
)


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
    assert client.get("/api/v1/admin/organizations").status_code == 401


def test_candidate_forbidden_from_every_admin_endpoint(client, auth_headers):
    """Phase 14: "Candidate cannot access Admin"."""
    assert client.get("/api/v1/admin/overview", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/users", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/jobs", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/activity", headers=auth_headers).status_code == 403
    assert (
        client.get("/api/v1/admin/organizations", headers=auth_headers).status_code
        == 403
    )


def test_recruiter_forbidden_from_admin_endpoints(client, recruiter_headers):
    """Phase 14: "Recruiter cannot access Admin"."""
    assert (
        client.get("/api/v1/admin/overview", headers=recruiter_headers).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/users", headers=recruiter_headers).status_code == 403
    )


def test_overview_with_no_data(client, admin_headers):
    response = client.get("/api/v1/admin/overview", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_users"] == 1  # the admin itself, the only registered user
    assert body["total_sessions"] == 0
    assert body["total_reports"] == 0
    assert body["avg_platform_score"] is None
    assert body["ai_usage"]["questions_generated"] == 0
    assert body["storage"]["audio_bytes"] == 0
    assert len(body["signups_last_30_days"]) == 30
    assert len(body["sessions_last_30_days"]) == 30


def test_overview_counts_completed_sessions_and_reports(
    client, admin_headers, db, registered_user
):
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
    )
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Frontend Engineer",
        final_score=6.0,
    )

    response = client.get("/api/v1/admin/overview", headers=admin_headers)
    body = response.json()

    assert body["total_sessions"] == 2
    assert body["sessions_by_status"]["completed"] == 2
    assert body["total_reports"] == 2
    assert body["avg_platform_score"] == 7.0


def test_overview_counts_draft_sessions_separately(
    client, admin_headers, db, registered_user
):
    draft = InterviewSession(
        user_id=uuid.UUID(registered_user["id"]),
        title="Draft session",
        job_role="Data Scientist",
        job_description="A role description long enough to pass validation checks here.",
        status=SESSION_STATUS_DRAFT,
    )
    db.add(draft)
    db.commit()

    response = client.get("/api/v1/admin/overview", headers=admin_headers)
    body = response.json()

    assert body["total_sessions"] == 1
    assert body["sessions_by_status"]["draft"] == 1
    assert body["sessions_by_status"]["completed"] == 0


def test_list_users_includes_registered_user(client, admin_headers, registered_user):
    response = client.get("/api/v1/admin/users", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()

    matches = [u for u in body["items"] if u["email"] == registered_user["email"]]
    assert len(matches) == 1
    user = matches[0]
    assert user["role"] == "candidate"
    assert user["organization_id"] is None
    assert user["is_active"] is True
    assert user["sessions_completed"] == 0
    assert user["latest_session_at"] is None


def test_list_users_search_filters_by_email(client, admin_headers, registered_user):
    match = client.get(
        "/api/v1/admin/users", params={"search": "alice"}, headers=admin_headers
    )
    assert any(u["email"] == registered_user["email"] for u in match.json()["items"])

    no_match = client.get(
        "/api/v1/admin/users", params={"search": "nobody-here"}, headers=admin_headers
    )
    assert no_match.json()["total"] == 0


def test_list_users_reflects_session_count(client, admin_headers, db, registered_user):
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
    )

    response = client.get("/api/v1/admin/users", headers=admin_headers)
    user = next(
        u for u in response.json()["items"] if u["email"] == registered_user["email"]
    )
    assert user["sessions_completed"] == 1
    assert user["latest_session_at"] is not None


def test_list_job_roles(client, admin_headers, db, registered_user):
    user_id = uuid.UUID(registered_user["id"])
    _make_completed_session(db, user_id, job_role="Backend Engineer", final_score=8.0)
    _make_completed_session(db, user_id, job_role="Backend Engineer", final_score=7.0)
    _make_completed_session(db, user_id, job_role="Frontend Engineer", final_score=6.0)

    response = client.get("/api/v1/admin/jobs", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()

    by_role = {row["role"]: row["session_count"] for row in body}
    assert by_role["Backend Engineer"] == 2
    assert by_role["Frontend Engineer"] == 1


def test_activity_includes_session_and_resume_events(
    client, admin_headers, db, registered_user
):
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

    response = client.get("/api/v1/admin/activity", headers=admin_headers)
    assert response.status_code == 200
    events = response.json()

    event_types = {e["event_type"] for e in events}
    assert "session_created" in event_types
    assert "report_generated" in event_types
    assert "resume_uploaded" in event_types


# ---------------------------------------------------------------------------
# Organization management (Phase 9)
# ---------------------------------------------------------------------------


def test_create_organization(client, admin_headers):
    response = client.post(
        "/api/v1/admin/organizations",
        json={"name": "Umbrella Corp"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Umbrella Corp"
    assert body["is_active"] is True
    assert body["recruiter_count"] == 0
    assert body["candidate_count"] == 0


def test_create_organization_rejects_duplicate_name(
    client, admin_headers, organization
):
    response = client.post(
        "/api/v1/admin/organizations",
        json={"name": organization.name},
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_create_organization_requires_admin(client, auth_headers):
    response = client.post(
        "/api/v1/admin/organizations",
        json={"name": "Umbrella Corp"},
        headers=auth_headers,
    )
    assert response.status_code == 403


def test_list_organizations_reflects_member_counts(
    client, admin_headers, organization, recruiter_user, org_candidate
):
    response = client.get("/api/v1/admin/organizations", headers=admin_headers)
    assert response.status_code == 200
    org = next(o for o in response.json()["items"] if o["id"] == str(organization.id))
    assert org["recruiter_count"] == 1
    assert org["candidate_count"] == 1


def test_deactivate_and_reactivate_organization(client, admin_headers, organization):
    deactivated = client.patch(
        f"/api/v1/admin/organizations/{organization.id}/deactivate",
        headers=admin_headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    reactivated = client.patch(
        f"/api/v1/admin/organizations/{organization.id}/activate", headers=admin_headers
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["is_active"] is True


# ---------------------------------------------------------------------------
# Recruiter provisioning (Phase 9)
# ---------------------------------------------------------------------------


def test_create_recruiter(client, admin_headers, organization):
    response = client.post(
        "/api/v1/admin/recruiters",
        json={
            "email": "new-recruiter@example.com",
            "password": "securepassword9",
            "full_name": "Nora New",
            "organization_id": str(organization.id),
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "recruiter"
    assert body["organization_id"] == str(organization.id)
    assert body["organization_name"] == organization.name

    # The new recruiter can actually log in and use the recruiter dashboard.
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "new-recruiter@example.com", "password": "securepassword9"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    candidates = client.get(
        "/api/v1/recruiter/candidates", headers={"Authorization": f"Bearer {token}"}
    )
    assert candidates.status_code == 200


def test_create_recruiter_rejects_unknown_organization(client, admin_headers):
    response = client.post(
        "/api/v1/admin/recruiters",
        json={
            "email": "new-recruiter@example.com",
            "password": "securepassword9",
            "full_name": "Nora New",
            "organization_id": str(uuid.uuid4()),
        },
        headers=admin_headers,
    )
    assert response.status_code == 404


def test_create_recruiter_requires_admin(client, auth_headers, organization):
    response = client.post(
        "/api/v1/admin/recruiters",
        json={
            "email": "new-recruiter@example.com",
            "password": "securepassword9",
            "full_name": "Nora New",
            "organization_id": str(organization.id),
        },
        headers=auth_headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# User activation (Phase 9)
# ---------------------------------------------------------------------------


def test_deactivate_user_blocks_further_access(client, admin_headers, recruiter_user):
    login = client.post(
        "/api/v1/auth/login",
        data={"username": "recruiter@example.com", "password": "securepassword3"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    deactivate = client.patch(
        f"/api/v1/admin/users/{recruiter_user['id']}/deactivate", headers=admin_headers
    )
    assert deactivate.status_code == 200

    # The recruiter's already-issued token is rejected immediately —
    # is_active is checked in get_current_user, not just at login.
    response = client.get("/api/v1/recruiter/candidates", headers=headers)
    assert response.status_code == 403


def test_admin_cannot_deactivate_own_account(client, admin_headers, admin_user):
    response = client.patch(
        f"/api/v1/admin/users/{admin_user['id']}/deactivate", headers=admin_headers
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Role assignment (Phase 2 — Super Admin only)
# ---------------------------------------------------------------------------


def test_admin_cannot_assign_roles(client, admin_headers, registered_user):
    """Only Super Admin may assign roles — plain Admin is forbidden."""
    response = client.patch(
        f"/api/v1/admin/users/{registered_user['id']}/role",
        json={"role": "recruiter"},
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_super_admin_can_assign_role(client, super_admin_headers, registered_user):
    response = client.patch(
        f"/api/v1/admin/users/{registered_user['id']}/role",
        json={"role": "recruiter"},
        headers=super_admin_headers,
    )
    assert response.status_code == 200

    # The change takes effect on the user's very next request/login,
    # without needing a separate cache-invalidation step.
    login = client.post(
        "/api/v1/auth/login",
        data={"username": registered_user["email"], "password": "securepassword1"},
    )
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["role"] == "recruiter"


def test_super_admin_cannot_change_own_role(
    client, super_admin_headers, super_admin_user
):
    response = client.patch(
        f"/api/v1/admin/users/{super_admin_user['id']}/role",
        json={"role": "candidate"},
        headers=super_admin_headers,
    )
    assert response.status_code == 400


def test_role_assignment_rejects_invalid_role(
    client, super_admin_headers, registered_user
):
    response = client.patch(
        f"/api/v1/admin/users/{registered_user['id']}/role",
        json={"role": "not-a-real-role"},
        headers=super_admin_headers,
    )
    assert response.status_code == 422
