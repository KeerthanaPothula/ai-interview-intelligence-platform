"""Seed realistic demo data for local development and demos (Phase 15).

Usage (from the backend/ directory, with DATABASE_URL etc. already set —
same environment the app itself runs with):

    python -m scripts.seed_demo_data

Idempotent: re-running is safe. Organizations and users are matched by
their unique name/email and left untouched if they already exist;
interview sessions are only generated once (skipped entirely if any
already exist in the database), so this never duplicates data on a
second run.

Creates:
  - 4 organizations (Google, Amazon, Microsoft, OpenAI).
  - The exact three demo accounts from the spec (password for all: "password"):
      Super Admin: admin@aiip.com
      Recruiter:   recruiter@google.com   (Google)
      Candidate:   candidate@example.com  (Google — invited, so the
                   recruiter demo account has at least one visible
                   candidate out of the box)
  - A few extra accounts (a second recruiter in a different org, a plain
    Admin, more candidates — some affiliated, some not) so multi-tenant
    isolation and the Admin's platform-wide view both have something real
    to look at, not just the three headline accounts.
  - Completed interview sessions + SessionReports for every candidate,
    with a spread of recruiter-pipeline statuses (applied through hired),
    so neither the Recruiter nor the Admin dashboard is empty.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.core.security import get_password_hash
from app.database import SessionLocal
from app.models.features import SessionReport
from app.models.interview import (
    RECRUITER_STATUS_APPLIED,
    RECRUITER_STATUS_HIRED,
    RECRUITER_STATUS_INTERVIEWED,
    RECRUITER_STATUS_REJECTED,
    RECRUITER_STATUS_REVIEWING,
    RECRUITER_STATUS_SHORTLISTED,
    SESSION_STATUS_COMPLETED,
    InterviewSession,
)
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User

DEMO_PASSWORD = "password"

ORG_NAMES = ["Google", "Amazon", "Microsoft", "OpenAI"]

JOB_ROLES = [
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Data Scientist",
    "DevOps Engineer",
    "Product Manager",
]

JOB_DESCRIPTION = (
    "We are looking for a talented engineer to join our team, working on "
    "scalable systems, collaborating cross-functionally, and shipping "
    "high-quality software used by millions of people."
)

READINESS_LEVELS = [
    "Beginner",
    "Developing",
    "Interview Ready",
    "Strong Candidate",
    "Highly Competitive",
]

# First entry is the exact "candidate@example.com" demo account from the
# spec; the rest exist purely to make the dashboards feel real.
CANDIDATES = [
    ("Cara Candidate", "candidate@example.com"),
    ("Alex Chen", "alex.chen@example.com"),
    ("Priya Patel", "priya.patel@example.com"),
    ("Marcus Johnson", "marcus.johnson@example.com"),
    ("Sofia Garcia", "sofia.garcia@example.com"),
    ("Wei Zhang", "wei.zhang@example.com"),
    ("Emma Wilson", "emma.wilson@example.com"),
    ("Noah Kim", "noah.kim@example.com"),
]

RECRUITER_STATUS_CYCLE = [
    RECRUITER_STATUS_APPLIED,
    RECRUITER_STATUS_REVIEWING,
    RECRUITER_STATUS_INTERVIEWED,
    RECRUITER_STATUS_SHORTLISTED,
    RECRUITER_STATUS_REJECTED,
    RECRUITER_STATUS_HIRED,
]


def get_or_create_organization(db, name: str) -> Organization:
    org = db.query(Organization).filter(Organization.name == name).first()
    if org is not None:
        return org
    org = Organization(name=name)
    db.add(org)
    db.flush()
    return org


def get_or_create_user(
    db, *, email: str, full_name: str, role: str, organization_id=None
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        return user
    user = User(
        email=email,
        hashed_password=get_password_hash(DEMO_PASSWORD),
        full_name=full_name,
        role=role,
        organization_id=organization_id,
    )
    db.add(user)
    db.flush()
    return user


def create_completed_session(
    db,
    *,
    user: User,
    job_role: str,
    days_ago: int,
    final_score: float,
    recruiter_status: str | None,
) -> InterviewSession:
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    session = InterviewSession(
        user_id=user.id,
        title=f"{job_role} Practice Interview",
        job_role=job_role,
        job_description=JOB_DESCRIPTION,
        status=SESSION_STATUS_COMPLETED,
        recruiter_status=recruiter_status,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(session)
    db.flush()

    def _jitter(base: float) -> float:
        return round(min(10.0, max(0.0, base + random.uniform(-1.2, 1.2))), 1)

    communication = _jitter(final_score)
    technical = _jitter(final_score)
    problem_solving = _jitter(final_score)
    readiness_index = min(len(READINESS_LEVELS) - 1, int(final_score // 2))

    report = SessionReport(
        session_id=session.id,
        overall_performance=(
            f"{user.full_name.split()[0]} demonstrated "
            f"{'strong' if final_score >= 7 else 'developing'} proficiency in this "
            f"{job_role} interview, with clear communication and "
            f"{'solid' if technical >= 7 else 'emerging'} technical depth."
        ),
        final_score=final_score,
        confidence_score=random.randint(55, 95),
        communication_score=communication,
        technical_score=technical,
        problem_solving_score=problem_solving,
        strengths='["Clear communication", "Structured problem-solving", "Relevant real-world examples"]',
        weaknesses='["Could elaborate more on trade-offs", "Deepen system design fundamentals"]',
        improvement_plan='["Practice system design weekly", "Review core data structures", "Do a mock interview every week"]',
        readiness_level=READINESS_LEVELS[readiness_index],
        model_used="gemini-2.0-flash",
    )
    db.add(report)
    return session


def main() -> None:
    db = SessionLocal()
    try:
        print("Seeding organizations...")
        orgs = {name: get_or_create_organization(db, name) for name in ORG_NAMES}
        db.flush()

        print("Seeding demo accounts...")
        super_admin = get_or_create_user(
            db,
            email="admin@aiip.com",
            full_name="Sam SuperAdmin",
            role=Role.SUPER_ADMIN.value,
        )
        recruiter = get_or_create_user(
            db,
            email="recruiter@google.com",
            full_name="Rita Recruiter",
            role=Role.RECRUITER.value,
            organization_id=orgs["Google"].id,
        )
        # A second recruiter in a different org — demonstrates that a
        # recruiter only ever sees their own organization's candidates
        # (Phase 3), not a hypothetical claim.
        get_or_create_user(
            db,
            email="recruiter@amazon.com",
            full_name="Ryan Recruiter",
            role=Role.RECRUITER.value,
            organization_id=orgs["Amazon"].id,
        )
        admin = get_or_create_user(
            db,
            email="ops-admin@aiip.com",
            full_name="Adam Admin",
            role=Role.ADMIN.value,
        )

        candidates: list[User] = []
        for i, (full_name, email) in enumerate(CANDIDATES):
            # The first 5 candidates are invited into Google (visible to
            # recruiter@google.com); the rest stay unaffiliated —
            # Phase 3: "candidate.organization = NULL" unless invited.
            org_id = orgs["Google"].id if i < 5 else None
            candidate = get_or_create_user(
                db,
                email=email,
                full_name=full_name,
                role=Role.CANDIDATE.value,
                organization_id=org_id,
            )
            candidates.append(candidate)
        db.flush()

        existing_sessions = db.query(InterviewSession).count()
        if existing_sessions == 0:
            print("Seeding interview sessions and reports...")
            for i, candidate in enumerate(candidates):
                num_sessions = random.randint(1, 3)
                for j in range(num_sessions):
                    is_latest = j == num_sessions - 1
                    create_completed_session(
                        db,
                        user=candidate,
                        job_role=random.choice(JOB_ROLES),
                        days_ago=random.randint(1, 45) + j * 3,
                        final_score=round(random.uniform(4.0, 9.5), 1),
                        # Only the candidate's latest session enters the
                        # recruiter pipeline with a real status — matches
                        # recruiter_service's "latest completed session
                        # per user" semantics.
                        recruiter_status=RECRUITER_STATUS_CYCLE[
                            i % len(RECRUITER_STATUS_CYCLE)
                        ]
                        if is_latest
                        else None,
                    )
        else:
            print(
                f"{existing_sessions} interview session(s) already exist — skipping session seed."
            )

        db.commit()

        print('\nDone. Demo accounts (password for all: "password"):')
        print(f"  Super Admin: {super_admin.email}")
        print(f"  Admin:       {admin.email}")
        print(f"  Recruiter:   {recruiter.email}  (organization: Google)")
        print("  Recruiter:   recruiter@amazon.com  (organization: Amazon)")
        print("  Candidate:   candidate@example.com  (organization: Google)")
        print(f"\n{len(orgs)} organizations, {len(candidates)} candidates seeded.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
