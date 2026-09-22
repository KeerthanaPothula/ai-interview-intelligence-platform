"""The Alembic migration chain, run against a real PostgreSQL database.

The rest of the suite builds its schema with ``Base.metadata.create_all`` on
in-memory SQLite, so nothing else ever executes the migrations, and SQLite
cannot tell us whether they work on PostgreSQL (production runs
``alembic upgrade head`` on Neon at every container start).

These tests only run when ``MIGRATION_TEST_DATABASE_URL`` points at a
PostgreSQL server (CI's ``backend-migrations`` job sets it; locally see
docs/TESTING.md). They never touch that database's contents: each test
creates its own uniquely named, empty database on the server and drops it
afterwards. Alembic runs as a subprocess, exactly as in the Dockerfile CMD, so
``alembic/env.py`` resolves ``DATABASE_URL`` the way it does in production.

The schema is created ONLY by the migrations; nothing here creates tables.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL, make_url

import app.models  # noqa: F401 — registers every table on Base.metadata
from app.database import Base

SERVER_URL = os.environ.get("MIGRATION_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not SERVER_URL,
    reason="MIGRATION_TEST_DATABASE_URL (a PostgreSQL server) is not set",
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"

# Named objects the migration chain is expected to have created, taken from the
# revisions that add them. Not exhaustive: the drift test below covers
# tables/columns/types/nullability generically, this pins named indexes,
# constraints and their behaviour.
EXPECTED_INDEXES: dict[str, set[str]] = {
    "users": {"ix_users_email", "ix_users_organization_id"},
    "organizations": {"ix_organizations_name"},
    "interview_sessions": {
        "ix_interview_sessions_user_id",
        "ix_interview_sessions_status",
    },
    "audio_responses": {"ix_audio_responses_session_id", "ix_audio_responses_status"},
    "refresh_tokens": {"ix_refresh_tokens_user_id", "ix_refresh_tokens_token_hash"},
    "password_reset_tokens": {
        "ix_password_reset_tokens_user_id",
        "ix_password_reset_tokens_token_hash",
    },
    "conversation_turns": {"ix_conversation_turns_audio_response_id"},
    "document_chunks": {"ix_document_chunks_resume_document_id"},
    "follow_up_questions": {
        "ix_follow_up_questions_session_id",
        "ix_follow_up_questions_original_question_id",
        "ix_follow_up_questions_parent_audio_response_id",
    },
}
EXPECTED_UNIQUE_INDEXES = {
    "ix_users_email",
    "ix_organizations_name",
    "ix_password_reset_tokens_token_hash",
}
EXPECTED_CHECKS = {
    "users": {"ck_users_role"},
    "interview_analyses": {"ck_analyses_overall_score"},
    "live_interview_sessions": {"ck_live_interview_sessions_status"},
    "conversation_turn_analyses": {"ck_turn_analyses_overall_score"},
}
# (table, constraint name, referred table, ON DELETE)
EXPECTED_FKS = [
    ("users", "fk_users_organization_id", "organizations", "SET NULL"),
    (
        "conversation_turns",
        "fk_conversation_turns_audio_response_id",
        "audio_responses",
        "SET NULL",
    ),
    (
        "interview_sessions",
        "fk_interview_sessions_live_session_id",
        "live_interview_sessions",
        "SET NULL",
    ),
]
EXPECTED_UNIQUE_CONSTRAINTS: dict[str, set[str]] = {
    "interview_sessions": {"uq_interview_sessions_live_session_id"},
    "conversation_turn_analyses": {"uq_conversation_turn_analyses_turn_id"},
}
# autogenerate operations that mean the migrated schema and the ORM models
# disagree about the shape of the data (as opposed to comments/index naming).
STRUCTURAL_DIFF_OPS = {
    "add_table",
    "remove_table",
    "add_column",
    "remove_column",
    "modify_type",
    "modify_nullable",
}


def _alembic(url: URL, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _ok(result: subprocess.CompletedProcess[str]) -> subprocess.CompletedProcess[str]:
    assert result.returncode == 0, (
        f"`alembic` exited {result.returncode}\n--- stdout ---\n{result.stdout}"
        f"\n--- stderr ---\n{result.stderr}"
    )
    return result


@contextmanager
def _empty_database():
    server = make_url(SERVER_URL)
    assert server.get_backend_name() == "postgresql", "need a PostgreSQL server URL"
    name = f"migtest_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    try:
        yield server.set(database=name)
    finally:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _expected_head() -> str:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"migration history has multiple heads: {heads}"
    return heads[0]


def _table_names(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


@pytest.fixture(scope="module")
def migrated():
    """A fresh empty database, upgraded once with `alembic upgrade head`."""
    with _empty_database() as url:
        engine = sa.create_engine(url)
        assert _table_names(engine) == set(), "database was not empty before migrating"
        first = _ok(_alembic(url, "upgrade", "head"))
        yield url, engine, first
        engine.dispose()


def test_server_is_postgresql(migrated):
    _, engine, _ = migrated
    with engine.connect() as conn:
        version = conn.execute(sa.text("SHOW server_version")).scalar_one()
    assert engine.dialect.name == "postgresql", version


def test_upgrade_head_applies_every_revision_and_reaches_expected_head(migrated):
    _, engine, first = migrated
    head = _expected_head()
    with engine.connect() as conn:
        versions = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).all()
    assert [v[0] for v in versions] == [head]

    revision_files = [p for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py"]
    applied = first.stderr.count("Running upgrade")
    assert applied == len(revision_files), (
        f"{len(revision_files)} revision files but {applied} were applied — "
        "a migration file is not part of the chain"
    )


def test_migrated_tables_match_the_models_exactly(migrated):
    _, engine, _ = migrated
    assert _table_names(engine) == set(Base.metadata.tables) | {"alembic_version"}


def test_expected_indexes_exist(migrated):
    _, engine, _ = migrated
    inspector = sa.inspect(engine)
    unique_seen: set[str] = set()
    for table, expected in EXPECTED_INDEXES.items():
        indexes = {ix["name"]: ix for ix in inspector.get_indexes(table)}
        assert expected <= set(indexes), f"{table}: missing {expected - set(indexes)}"
        unique_seen |= {n for n, ix in indexes.items() if ix["unique"]}
    assert EXPECTED_UNIQUE_INDEXES <= unique_seen


def test_expected_check_and_foreign_key_constraints_exist(migrated):
    _, engine, _ = migrated
    inspector = sa.inspect(engine)
    for table, expected in EXPECTED_CHECKS.items():
        names = {c["name"] for c in inspector.get_check_constraints(table)}
        assert expected <= names, f"{table}: missing check {expected - names}"
    for table, name, referred, on_delete in EXPECTED_FKS:
        fks = {fk["name"]: fk for fk in inspector.get_foreign_keys(table)}
        assert name in fks, f"{table}: missing foreign key {name}"
        assert fks[name]["referred_table"] == referred
        assert fks[name]["options"].get("ondelete") == on_delete


def test_expected_unique_constraints_exist(migrated):
    _, engine, _ = migrated
    inspector = sa.inspect(engine)
    for table, expected in EXPECTED_UNIQUE_CONSTRAINTS.items():
        names = {c["name"] for c in inspector.get_unique_constraints(table)}
        assert expected <= names, f"{table}: missing unique constraint {expected - names}"


def test_live_session_id_unique_constraint_is_enforced_by_postgresql(migrated):
    """Two InterviewSession rows cannot mirror the same LiveInterviewSession —
    this is what makes end_interview's mirroring idempotent under a race."""
    _, engine, _ = migrated
    user_id = uuid.uuid4()
    live_session_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, hashed_password, full_name, role) "
                "VALUES (:id, 'mig-user@example.com', 'x', 'Migration Test', 'candidate')"
            ),
            {"id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO live_interview_sessions "
                "(id, user_id, job_role, job_description) "
                "VALUES (:id, :user_id, 'Engineer', 'A role.')"
            ),
            {"id": live_session_id, "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO interview_sessions "
                "(id, user_id, title, job_role, job_description, status, live_session_id) "
                "VALUES (:id, :user_id, 'Live Interview', 'Engineer', 'A role.', "
                "'completed', :live_session_id)"
            ),
            {"id": uuid.uuid4(), "user_id": user_id, "live_session_id": live_session_id},
        )
    with pytest.raises(sa.exc.IntegrityError, match="uq_interview_sessions_live_session_id"):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO interview_sessions "
                    "(id, user_id, title, job_role, job_description, status, live_session_id) "
                    "VALUES (:id, :user_id, 'Live Interview', 'Engineer', 'A role.', "
                    "'completed', :live_session_id)"
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "live_session_id": live_session_id,
                },
            )


def test_role_check_constraint_is_enforced_by_postgresql(migrated):
    _, engine, _ = migrated
    insert = sa.text(
        "INSERT INTO users (id, email, hashed_password, full_name, role) "
        "VALUES (:id, :email, 'x', 'Migration Test', :role)"
    )
    with engine.begin() as conn:  # a valid role is accepted...
        conn.execute(
            insert, {"id": uuid.uuid4(), "email": "ok@example.com", "role": "candidate"}
        )
    with pytest.raises(
        sa.exc.IntegrityError, match="ck_users_role"
    ):  # ...an invalid one is not
        with engine.begin() as conn:
            conn.execute(
                insert,
                {"id": uuid.uuid4(), "email": "bad@example.com", "role": "wizard"},
            )


def test_migrated_schema_has_no_structural_drift_from_the_models(migrated):
    """Columns/types/nullability/tables produced by the migrations equal the ORM's.

    Deliberately not asserting an empty diff: the chain currently differs from
    the models in comment-only and index-naming ways that change no behaviour
    (see docs/TESTING.md). A missing or mistyped column is what breaks the
    app, and that is what this checks.
    """
    _, engine, _ = migrated
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    operations = [
        op for item in diff for op in (item if isinstance(item, list) else [item])
    ]
    structural = [op for op in operations if op[0] in STRUCTURAL_DIFF_OPS]
    assert not structural, f"migrations and models disagree: {structural}"


def test_second_upgrade_head_is_a_noop(migrated):
    url, engine, _ = migrated
    again = _ok(_alembic(url, "upgrade", "head"))
    assert "Running upgrade" not in again.stderr
    with engine.connect() as conn:
        versions = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).all()
    assert [v[0] for v in versions] == [_expected_head()]
    assert _expected_head() in _ok(_alembic(url, "current")).stdout


def test_downgrade_to_base_then_upgrade_again_round_trips():
    with _empty_database() as url:
        engine = sa.create_engine(url)
        try:
            _ok(_alembic(url, "upgrade", "head"))
            _ok(_alembic(url, "downgrade", "base"))
            assert _table_names(engine) == {"alembic_version"}
            _ok(_alembic(url, "upgrade", "head"))
            assert _table_names(engine) == set(Base.metadata.tables) | {
                "alembic_version"
            }
        finally:
            engine.dispose()
