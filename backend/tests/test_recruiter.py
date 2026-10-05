"""Tests for GET/PATCH /api/v1/recruiter/candidates — RBAC + org isolation."""

import uuid
from datetime import datetime, timezone

from app.models.features import SessionReport
from app.models.interview import SESSION_STATUS_COMPLETED, InterviewSession
from app.models.user import User
from tests.conftest import (
    ORG_CANDIDATE_USER,
    OTHER_USER,
    _login,
    _register_with_role,
)


def _make_completed_session(
    db,
    user_id,
    *,
    job_role,
    final_score,
    communication,
    technical,
    created_at=None,
    recruiter_status=None,
):
    session = InterviewSession(
        user_id=user_id,
        title="Completed Interview",
        job_role=job_role,
        job_description="A role description long enough to pass validation checks here.",
        status=SESSION_STATUS_COMPLETED,
        recruiter_status=recruiter_status,
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


def test_candidate_forbidden(client, auth_headers):
    """A plain CANDIDATE (auth_headers/registered_user) must never reach
    the recruiter dashboard — Phase 14: "Candidate cannot access
    Recruiter"."""
    response = client.get("/api/v1/recruiter/candidates", headers=auth_headers)
    assert response.status_code == 403


def test_empty_when_no_completed_sessions(client, recruiter_headers):
    response = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["summary"]["total_candidates"] == 0
    assert body["summary"]["avg_interview_score"] is None


def test_lists_candidate_from_completed_session(
    client, recruiter_headers, db, org_candidate
):
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.5,
        communication=9.0,
        technical=8.0,
    )

    response = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 1
    candidate = body["items"][0]
    assert candidate["name"] == org_candidate["full_name"]
    assert candidate["role"] == "Backend Engineer"
    assert candidate["interview_score"] == 85
    assert candidate["communication"] == 90
    assert candidate["technical"] == 80
    # New candidates default to "applied" — status is persisted
    # (InterviewSession.recruiter_status), not derived from the score.
    assert candidate["status"] == "applied"
    assert candidate["resume_score"] is None
    assert body["summary"]["total_candidates"] == 1


def test_uses_latest_completed_session_per_user(
    client, recruiter_headers, db, org_candidate
):
    user_id = uuid.UUID(org_candidate["id"])
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

    response = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    body = response.json()

    assert body["total"] == 1
    candidate = body["items"][0]
    assert candidate["role"] == "New Role"
    assert candidate["sessions_completed"] == 2


def test_search_filters_by_role(client, recruiter_headers, db, org_candidate):
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    match = client.get(
        "/api/v1/recruiter/candidates",
        params={"search": "backend"},
        headers=recruiter_headers,
    )
    assert match.json()["total"] == 1

    no_match = client.get(
        "/api/v1/recruiter/candidates",
        params={"search": "frontend"},
        headers=recruiter_headers,
    )
    assert no_match.json()["total"] == 0


def test_status_filter(client, recruiter_headers, db, org_candidate):
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
        recruiter_status="shortlisted",
    )

    shortlisted = client.get(
        "/api/v1/recruiter/candidates",
        params={"status": "shortlisted"},
        headers=recruiter_headers,
    )
    assert shortlisted.json()["total"] == 1

    applied = client.get(
        "/api/v1/recruiter/candidates",
        params={"status": "applied"},
        headers=recruiter_headers,
    )
    assert applied.json()["total"] == 0


def test_pagination(client, recruiter_headers, db, org_candidate):
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.get(
        "/api/v1/recruiter/candidates",
        params={"skip": 0, "limit": 1},
        headers=recruiter_headers,
    )
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1

    response = client.get(
        "/api/v1/recruiter/candidates",
        params={"skip": 1, "limit": 1},
        headers=recruiter_headers,
    )
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Multi-tenant organization isolation
# ---------------------------------------------------------------------------


def test_recruiter_cannot_see_other_organizations_candidates(
    client, db, org_candidate, other_org_recruiter_headers
):
    """org_candidate belongs to `organization`; other_org_recruiter_headers
    belongs to `other_organization` — must see zero candidates."""
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.get(
        "/api/v1/recruiter/candidates", headers=other_org_recruiter_headers
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_recruiter_never_sees_unaffiliated_candidate(
    client, db, recruiter_headers, registered_user
):
    """registered_user (VALID_USER) has organization_id=None — an
    unaffiliated candidate must never appear to any recruiter, regardless
    of organization."""
    _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert response.json()["total"] == 0


def test_admin_sees_candidates_across_every_organization(
    client, db, org_candidate, admin_headers
):
    """Admin/Super Admin are platform-wide, unlike Recruiter — Phase 3:
    "Super Admin can see every organization" (Admin shares this visibility
    per Phase 9's org-management scope)."""
    _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.get("/api/v1/recruiter/candidates", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1


# ---------------------------------------------------------------------------
# PATCH /recruiter/candidates/{session_id}/status
# ---------------------------------------------------------------------------


def test_update_candidate_status(client, db, org_candidate, recruiter_headers):
    session = _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "shortlisted"},
        headers=recruiter_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "shortlisted"

    # Persisted, not ephemeral.
    listing = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert listing.json()["items"][0]["status"] == "shortlisted"


def test_update_candidate_status_rejects_invalid_value(
    client, db, org_candidate, recruiter_headers
):
    session = _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "not-a-real-status"},
        headers=recruiter_headers,
    )
    assert response.status_code == 422


def test_update_candidate_status_cross_org_returns_404(
    client, db, org_candidate, other_org_recruiter_headers
):
    """A recruiter from a different organization cannot change this
    candidate's status — 404 (not 403), so org membership can't be probed
    by comparing 403 vs 404 responses."""
    session = _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "shortlisted"},
        headers=other_org_recruiter_headers,
    )
    assert response.status_code == 404


def test_update_candidate_status_requires_recruiter_or_admin(
    client, db, org_candidate, auth_headers
):
    session = _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )

    response = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "shortlisted"},
        headers=auth_headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# "Open report": GET /interviews/{id} and GET /interviews/{id}/report
# ---------------------------------------------------------------------------


def _org_report_session(db, org_candidate):
    return _make_completed_session(
        db,
        uuid.UUID(org_candidate["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=7.0,
    )


def _open_report(client, session_id, headers):
    """The two reads the report page needs: session header + report."""
    return (
        client.get(f"/api/v1/interviews/{session_id}", headers=headers),
        client.get(f"/api/v1/interviews/{session_id}/report", headers=headers),
    )


def _assert_hidden(client, session_id, headers):
    """404 with exactly the body a nonexistent session gets — nothing leaks."""
    for resp, missing in zip(
        _open_report(client, session_id, headers),
        _open_report(client, uuid.uuid4(), headers),
    ):
        assert resp.status_code == 404, resp.text
        assert resp.json() == missing.json()


def test_recruiter_opens_report_for_same_org_candidate(
    client, db, org_candidate, recruiter_headers
):
    session = _org_report_session(db, org_candidate)

    detail, report = _open_report(client, session.id, recruiter_headers)

    assert detail.status_code == 200, detail.text
    assert detail.json()["user_id"] == org_candidate["id"]
    assert report.status_code == 200, report.text
    assert report.json()["session_id"] == str(session.id)
    assert float(report.json()["final_score"]) == 8.0


def test_recruiter_cannot_open_another_organizations_report(
    client, db, org_candidate, other_org_recruiter_headers
):
    session = _org_report_session(db, org_candidate)
    _assert_hidden(client, session.id, other_org_recruiter_headers)


def test_recruiter_cannot_open_unaffiliated_candidates_report(
    client, db, registered_user, recruiter_headers
):
    session = _make_completed_session(
        db,
        uuid.UUID(registered_user["id"]),
        job_role="Backend Engineer",
        final_score=8.0,
        communication=8.0,
        technical=8.0,
    )
    _assert_hidden(client, session.id, recruiter_headers)


def test_recruiter_cannot_open_a_session_outside_the_pipeline(
    client, db, org_candidate, recruiter_headers
):
    """Same org, but never completed + reported: not a pipeline candidate."""
    draft = InterviewSession(
        user_id=uuid.UUID(org_candidate["id"]),
        title="Draft",
        job_role="Backend Engineer",
        job_description="A role description long enough to pass validation checks.",
    )
    db.add(draft)
    db.commit()
    _assert_hidden(client, draft.id, recruiter_headers)


def test_recruiter_without_an_organization_cannot_open_reports(
    client, db, org_candidate, recruiter_user, recruiter_headers
):
    session = _org_report_session(db, org_candidate)
    user = db.get(User, uuid.UUID(recruiter_user["id"]))
    user.organization_id = None
    db.commit()
    _assert_hidden(client, session.id, recruiter_headers)


def test_recruiter_without_an_organization_sees_and_updates_nothing(
    client, db, org_candidate, recruiter_user, recruiter_headers
):
    """Fail closed: scope_organization_id returns None for an org-less
    recruiter, which has_candidate_access must not treat as platform-wide."""
    session = _org_report_session(db, org_candidate)
    user = db.get(User, uuid.UUID(recruiter_user["id"]))
    user.organization_id = None
    db.commit()

    listing = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    assert listing.json()["items"] == []

    update = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "shortlisted"},
        headers=recruiter_headers,
    )
    assert update.status_code == 404
    db.expire_all()
    assert db.get(InterviewSession, session.id).recruiter_status is None


def test_admin_updates_candidate_status_across_organizations(
    client, db, org_candidate, admin_headers
):
    session = _org_report_session(db, org_candidate)

    response = client.patch(
        f"/api/v1/recruiter/candidates/{session.id}/status",
        json={"status": "shortlisted"},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "shortlisted"


def test_readiness_and_coaching_stay_owner_only_for_pipeline_viewers(
    client, db, org_candidate, recruiter_headers, admin_headers
):
    """Pipeline viewers can open the report, not the candidate's readiness or
    coaching data (owner-only via interview_service.get_session_or_404)."""
    session = _org_report_session(db, org_candidate)

    for headers in (recruiter_headers, admin_headers):
        for path in ("readiness", "coaching-plan"):
            url = f"/api/v1/interviews/{session.id}/{path}"
            assert client.get(url, headers=headers).status_code == 404
            assert client.post(url, headers=headers).status_code == 404


def test_candidate_keeps_owner_only_access(
    client, db, org_candidate, organization, auth_headers
):
    session = _org_report_session(db, org_candidate)

    own_headers = {"Authorization": f"Bearer {_login(client, ORG_CANDIDATE_USER)}"}
    detail, report = _open_report(client, session.id, own_headers)
    assert (detail.status_code, report.status_code) == (200, 200)

    # Another candidate, even in the same organization, gets the owner 404.
    _register_with_role(client, db, OTHER_USER, organization_id=organization.id)
    mate_headers = {"Authorization": f"Bearer {_login(client, OTHER_USER)}"}
    _assert_hidden(client, session.id, mate_headers)
    _assert_hidden(client, session.id, auth_headers)


def test_open_report_requires_authentication(client, db, org_candidate):
    session = _org_report_session(db, org_candidate)
    for resp in _open_report(client, session.id, {}):
        assert resp.status_code == 401


def test_admin_and_super_admin_open_reports_across_organizations(
    client, db, org_candidate, admin_headers, super_admin_headers
):
    """Same platform-wide scope they already have on the candidate list."""
    session = _org_report_session(db, org_candidate)
    for headers in (admin_headers, super_admin_headers):
        detail, report = _open_report(client, session.id, headers)
        assert (detail.status_code, report.status_code) == (200, 200)


def test_recruiter_access_is_read_only(client, db, org_candidate, recruiter_headers):
    """Direct API: generating/regenerating and the candidate's readiness and
    coaching stay owner-only — the recruiter gets the owner lookup's 404."""
    session = _org_report_session(db, org_candidate)

    assert (
        client.post(
            f"/api/v1/interviews/{session.id}/report/generate",
            headers=recruiter_headers,
        ).status_code
        == 404
    )
    for path in ("readiness", "coaching-plan"):
        resp = client.get(
            f"/api/v1/interviews/{session.id}/{path}", headers=recruiter_headers
        )
        assert resp.status_code == 404, (path, resp.text)
    resp = client.patch(
        f"/api/v1/interviews/{session.id}",
        json={"title": "Renamed"},
        headers=recruiter_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Deactivating an organization blocks its recruiters
# ---------------------------------------------------------------------------

_ORG_DEACTIVATED = "Your organization has been deactivated."


def _set_org_active(client, admin_headers, organization, active):
    action = "activate" if active else "deactivate"
    resp = client.patch(
        f"/api/v1/admin/organizations/{organization.id}/{action}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text


def test_deactivating_an_organization_blocks_its_recruiters_until_reactivated(
    client, db, organization, org_candidate, recruiter_headers, admin_headers
):
    session = _org_report_session(db, org_candidate)
    candidates = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert candidates.json()["total"] == 1  # access works while active

    _set_org_active(client, admin_headers, organization, active=False)

    # The recruiter's still-valid token no longer reaches candidate data.
    for method, path, body in (
        ("GET", "/api/v1/recruiter/candidates", None),
        ("GET", f"/api/v1/interviews/{session.id}/report", None),
        ("GET", f"/api/v1/interviews/{session.id}", None),
        (
            "PATCH",
            f"/api/v1/recruiter/candidates/{session.id}/status",
            {"status": "shortlisted"},
        ),
        ("GET", "/api/v1/auth/me", None),
    ):
        resp = client.request(method, path, json=body, headers=recruiter_headers)
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["detail"] == _ORG_DEACTIVATED
    db.refresh(session)
    assert session.recruiter_status != "shortlisted"

    _set_org_active(client, admin_headers, organization, active=True)

    restored = client.get("/api/v1/recruiter/candidates", headers=recruiter_headers)
    assert restored.status_code == 200
    assert restored.json()["total"] == 1


def test_other_organizations_recruiters_are_unaffected(
    client, organization, other_org_recruiter_headers, admin_headers
):
    _set_org_active(client, admin_headers, organization, active=False)
    resp = client.get(
        "/api/v1/recruiter/candidates", headers=other_org_recruiter_headers
    )
    assert resp.status_code == 200


def test_candidates_of_a_deactivated_organization_keep_their_own_access(
    client, db, organization, org_candidate, admin_headers
):
    session = _org_report_session(db, org_candidate)
    _set_org_active(client, admin_headers, organization, active=False)

    own = {"Authorization": f"Bearer {_login(client, ORG_CANDIDATE_USER)}"}
    assert client.get("/api/v1/auth/me", headers=own).status_code == 200
    detail, report = _open_report(client, session.id, own)
    assert (detail.status_code, report.status_code) == (200, 200)


def test_admins_are_not_blocked_by_their_organizations_status(
    client, db, organization, admin_user, admin_headers, org_candidate
):
    """Platform-wide roles must never lock themselves out by deactivating the
    organization they happen to belong to."""
    admin = db.get(User, uuid.UUID(admin_user["id"]))
    admin.organization_id = organization.id
    db.commit()
    _org_report_session(db, org_candidate)

    _set_org_active(client, admin_headers, organization, active=False)

    assert (
        client.get("/api/v1/admin/overview", headers=admin_headers).status_code == 200
    )
    candidates = client.get("/api/v1/recruiter/candidates", headers=admin_headers)
    assert candidates.status_code == 200
    _set_org_active(client, admin_headers, organization, active=True)
