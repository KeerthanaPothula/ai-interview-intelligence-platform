"""Cross-cutting RBAC tests not tied to a single router.

test_admin.py and test_recruiter.py already cover "Candidate cannot access
Recruiter/Admin" and "Recruiter cannot access Admin" for their own
endpoints. This file covers the remaining Phase 14 requirements:
  - Recruiter cannot create interviews.
  - Admin cannot take interviews.
  - Registration always assigns CANDIDATE, and a client-supplied `role`
    field is silently ignored rather than honored (no self-service
    privilege escalation at signup).
  - Super Admin — the one role with no page/action it's excluded from —
    can do everything a Candidate, Recruiter, or Admin can.
"""

SESSION_PAYLOAD = {
    "title": "Backend Engineer Practice",
    "job_role": "Backend Engineer",
    "job_description": "A role description long enough to pass validation checks here.",
}


def test_recruiter_cannot_create_interviews(client, recruiter_headers):
    response = client.post(
        "/api/v1/interviews/", json=SESSION_PAYLOAD, headers=recruiter_headers
    )
    assert response.status_code == 403


def test_admin_cannot_create_interviews(client, admin_headers):
    """Phase 14: "Admin cannot take interviews"."""
    response = client.post(
        "/api/v1/interviews/", json=SESSION_PAYLOAD, headers=admin_headers
    )
    assert response.status_code == 403


def test_recruiter_cannot_start_live_interview(client, recruiter_headers):
    response = client.post(
        "/api/v1/live-interviews/",
        json={
            "job_role": "Backend Engineer",
            "job_description": "A role description long enough to pass validation checks here.",
            "max_turns": 5,
        },
        headers=recruiter_headers,
    )
    assert response.status_code == 403


def test_admin_cannot_upload_resume(client, admin_headers):
    response = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=admin_headers,
    )
    assert response.status_code == 403


def test_candidate_can_create_interviews(client, auth_headers):
    """Sanity check: the gate is role-specific, not a blanket lockout — a
    plain Candidate must still be able to use their own workflow."""
    response = client.post(
        "/api/v1/interviews/", json=SESSION_PAYLOAD, headers=auth_headers
    )
    assert response.status_code == 201


def test_super_admin_can_create_interviews(client, super_admin_headers):
    """Phase 4: "Super Admin: Everything." — the one role excluded from
    nothing, including the candidate workflow."""
    response = client.post(
        "/api/v1/interviews/", json=SESSION_PAYLOAD, headers=super_admin_headers
    )
    assert response.status_code == 201


def test_super_admin_can_view_candidates(client, super_admin_headers):
    response = client.get("/api/v1/recruiter/candidates", headers=super_admin_headers)
    assert response.status_code == 200


def test_super_admin_can_view_platform_overview(client, super_admin_headers):
    response = client.get("/api/v1/admin/overview", headers=super_admin_headers)
    assert response.status_code == 200


def test_unauthenticated_requests_return_401_not_403(client):
    """401 (no/invalid credentials) is distinct from 403 (valid credentials,
    insufficient role) — both are "unauthorized" colloquially, but callers
    need to tell "log in" from "you don't have permission" apart."""
    assert client.post("/api/v1/interviews/", json=SESSION_PAYLOAD).status_code == 401
    assert client.get("/api/v1/recruiter/candidates").status_code == 401
    assert client.get("/api/v1/admin/overview").status_code == 401


# ---------------------------------------------------------------------------
# Registration always assigns CANDIDATE — Phase 2
# ---------------------------------------------------------------------------


def test_registration_assigns_candidate_role(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newcandidate@example.com",
            "password": "securepassword7",
            "full_name": "New Candidate",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "candidate"
    assert response.json()["organization"] is None


def test_registration_ignores_client_supplied_role(client):
    """UserCreate has no `role` field — extra fields are silently dropped
    by Pydantic (the default, not an error), so a client cannot even
    attempt privilege escalation by adding one to the request body."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "sneaky@example.com",
            "password": "securepassword8",
            "full_name": "Sneaky Signup",
            "role": "super_admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "candidate"
