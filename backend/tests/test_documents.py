"""Tests for document upload and RAG question generation endpoints."""

import io
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from app.config import get_settings

_EXTRACTED_TEXT = (
    "Experienced Python engineer with 5 years of FastAPI and PostgreSQL expertise."
)
_RAG_QUESTIONS = [
    {
        "body": "Tell me about your FastAPI experience.",
        "category": "technical",
        "sequence_order": 1,
    },
    {
        "body": "How have you optimised PostgreSQL queries?",
        "category": "technical",
        "sequence_order": 2,
    },
    {
        "body": "Describe a challenging project.",
        "category": "behavioral",
        "sequence_order": 3,
    },
    {
        "body": "How do you handle deadlines?",
        "category": "situational",
        "sequence_order": 4,
    },
    {
        "body": "Walk me through a system you designed.",
        "category": "technical",
        "sequence_order": 5,
    },
]


def _mock_extract(file_path, mime_type):
    return _EXTRACTED_TEXT


def _mock_rag_questions(**kwargs):
    return _RAG_QUESTIONS.copy()


def _make_pdf():
    return io.BytesIO(b"%PDF-1.4 fake pdf content " + b"x" * 2048)


def _make_docx():
    return io.BytesIO(b"PK" + b"\x00" * 100 + b"fake docx content" + b"x" * 2000)


# ---------------------------------------------------------------------------
# POST /api/v1/documents/resume/upload
# ---------------------------------------------------------------------------


def test_upload_resume_pdf_success(client, auth_headers, upload_dir, monkeypatch):
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        _mock_extract,
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.chunk_text",
        lambda text, **kw: [text[:100], text[50:]],
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.store_chunks",
        lambda **kw: 2,
    )

    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.pdf", _make_pdf(), "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["filename"] == "resume.pdf"
    assert data["extracted_text"] == _EXTRACTED_TEXT
    assert data["chunk_count"] == 2


def test_upload_resume_unsupported_type(client, auth_headers):
    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.txt", io.BytesIO(b"plain text"), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_upload_resume_requires_auth(client):
    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.pdf", _make_pdf(), "application/pdf")},
    )
    assert resp.status_code == 401


def test_upload_resume_spoofed_content_returns_422(client, auth_headers):
    """Content-Type claims application/pdf but the bytes don't start with
    the PDF magic bytes (%PDF) — the Phase 3 magic-byte check must reject
    this even though the declared MIME type passed the allow-list check."""
    spoofed = io.BytesIO(b"not actually a pdf file" + b"x" * 2048)
    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.pdf", spoofed, "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_upload_resume_oversized_returns_413(client, auth_headers, monkeypatch):
    monkeypatch.setenv("MAX_RESUME_UPLOAD_SIZE_MB", "1")
    get_settings.cache_clear()

    oversized = io.BytesIO(b"%PDF-1.4 " + b"x" * (2 * 1024 * 1024))
    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("resume.pdf", oversized, "application/pdf")},
        headers=auth_headers,
    )

    get_settings.cache_clear()
    assert resp.status_code == 413


def test_upload_resume_sanitizes_path_traversal_filename(
    client, auth_headers, upload_dir, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        _mock_extract,
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.chunk_text", lambda text, **kw: [text]
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.store_chunks", lambda **kw: 1
    )

    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("../../etc/passwd.pdf", _make_pdf(), "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "/" not in data["filename"]
    assert ".." not in data["filename"]


# ---------------------------------------------------------------------------
# GET /api/v1/documents/resume/current
# ---------------------------------------------------------------------------


def test_get_current_resume_not_found(client, auth_headers):
    resp = client.get("/api/v1/documents/resume/current", headers=auth_headers)
    assert resp.status_code == 404


def test_get_current_resume_after_upload(client, auth_headers, upload_dir, monkeypatch):
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        _mock_extract,
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.chunk_text", lambda text, **kw: [text]
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.store_chunks", lambda **kw: 1
    )

    client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("cv.pdf", _make_pdf(), "application/pdf")},
        headers=auth_headers,
    )

    resp = client.get("/api/v1/documents/resume/current", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "cv.pdf"


def test_get_current_resume_requires_auth(client):
    resp = client.get("/api/v1/documents/resume/current")
    assert resp.status_code == 401


def test_resume_analysis_is_cached_until_explicitly_forced(
    client, auth_headers, upload_dir, monkeypatch
):
    _upload(client, auth_headers, monkeypatch, "cv.pdf", "Python and SQL experience.")
    calls = []

    def fake_analysis(prompt):
        calls.append(prompt)
        score = 88 if len(calls) == 1 else 90
        return f'{{"ats_score": {score}, "skills": ["Python"], "missing_skills": [], "keywords": ["SQL"], "suggestions": []}}'

    monkeypatch.setattr("app.services.gemini_service.generate_text", fake_analysis)
    path = "/api/v1/documents/resume/analysis"
    first = client.get(path, headers=auth_headers)
    second = client.get(path, headers=auth_headers)
    forced = client.get(f"{path}?force=true", headers=auth_headers)

    assert first.status_code == second.status_code == forced.status_code == 200
    assert first.json()["ats_score"] == second.json()["ats_score"] == 88
    assert forced.json()["ats_score"] == 90
    assert len(calls) == 2


def test_new_resume_gets_a_separate_analysis_cache(
    client, auth_headers, upload_dir, db, monkeypatch
):
    from app.models.documents import ResumeDocument

    first_resume = _upload(client, auth_headers, monkeypatch, "old.pdf", "Python resume.")
    first_row = db.get(ResumeDocument, uuid.UUID(first_resume["id"]))
    first_row.created_at = datetime(2000, 1, 1)
    db.commit()
    calls = []

    def fake_analysis(prompt):
        calls.append(prompt)
        score = 80 + len(calls)
        return f'{{"ats_score": {score}, "skills": [], "missing_skills": [], "keywords": [], "suggestions": []}}'

    monkeypatch.setattr("app.services.gemini_service.generate_text", fake_analysis)
    path = "/api/v1/documents/resume/analysis"
    assert client.get(path, headers=auth_headers).json()["ats_score"] == 81

    second_resume = _upload(client, auth_headers, monkeypatch, "new.pdf", "SQL resume.")
    assert second_resume["id"] != first_resume["id"]
    assert client.get(path, headers=auth_headers).json()["ats_score"] == 82
    assert len(calls) == 2


def test_failed_forced_analysis_preserves_previous_cache(
    client, auth_headers, upload_dir, monkeypatch
):
    _upload(client, auth_headers, monkeypatch, "cv.pdf", "Python resume.")
    monkeypatch.setattr(
        "app.services.gemini_service.generate_text",
        lambda prompt: '{"ats_score": 91, "skills": [], "missing_skills": [], "keywords": [], "suggestions": []}',
    )
    path = "/api/v1/documents/resume/analysis"
    assert client.get(path, headers=auth_headers).json()["ats_score"] == 91

    def unavailable(prompt):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("app.services.gemini_service.generate_text", unavailable)
    forced = client.get(f"{path}?force=true", headers=auth_headers)
    cached = client.get(path, headers=auth_headers)
    assert forced.status_code == cached.status_code == 200
    assert forced.json()["ats_score"] == cached.json()["ats_score"] == 91


# ---------------------------------------------------------------------------
# POST /api/v1/documents/interviews/{session_id}/generate-rag-questions
# ---------------------------------------------------------------------------


def test_generate_rag_questions_success(
    client, auth_headers, interview_session, upload_dir, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        _mock_extract,
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.chunk_text", lambda text, **kw: [text]
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.store_chunks", lambda **kw: 1
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.retrieve_relevant_chunks",
        lambda **kw: [_EXTRACTED_TEXT],
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.generate_rag_questions",
        _mock_rag_questions,
    )

    # Upload resume first
    client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("cv.pdf", _make_pdf(), "application/pdf")},
        headers=auth_headers,
    )

    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["session_id"] == str(interview_session.id)
    assert len(data["questions"]) == 5
    assert data["resume_context_used"] is True


def test_generate_rag_questions_no_resume(
    client, auth_headers, interview_session, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.documents.rag_service.retrieve_relevant_chunks",
        lambda **kw: [],
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.generate_rag_questions",
        _mock_rag_questions,
    )

    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["resume_context_used"] is False


def test_generate_rag_questions_wrong_session(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.routers.documents.rag_service.retrieve_relevant_chunks",
        lambda **kw: [],
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.generate_rag_questions",
        _mock_rag_questions,
    )
    resp = client.post(
        f"/api/v1/documents/interviews/{uuid.uuid4()}/generate-rag-questions",
        json={"count": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_generate_rag_questions_requires_auth(client, interview_session):
    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
    )
    assert resp.status_code == 401


def _forbid_rag_calls(monkeypatch):
    """Fail the test if the endpoint reaches retrieval or Gemini."""

    def _boom(**kwargs):
        raise AssertionError("RAG pipeline must not run for a rejected request")

    monkeypatch.setattr(
        "app.routers.documents.rag_service.retrieve_relevant_chunks", _boom
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.generate_rag_questions", _boom
    )


def _assert_question_and_answer_intact(db, interview_question, audio_response):
    from app.models.analysis import AudioResponse
    from app.models.interview import Question

    db.expire_all()
    assert db.get(Question, interview_question.id) is not None
    assert db.get(AudioResponse, audio_response.id) is not None


@pytest.mark.parametrize("status", ["in_progress", "processing", "completed"])
def test_generate_rag_questions_rejects_non_draft_session(
    client,
    auth_headers,
    db,
    interview_session,
    interview_question,
    audio_response,
    monkeypatch,
    status,
):
    """Replacing questions cascade-deletes recorded answers, so — like
    POST /interviews/{id}/questions/generate — only drafts are allowed."""
    interview_session.status = status
    db.commit()
    _forbid_rag_calls(monkeypatch)

    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
        headers=auth_headers,
    )

    assert resp.status_code == 409
    assert (
        resp.json()["detail"] == "Questions can only be generated for draft sessions."
    )
    _assert_question_and_answer_intact(db, interview_question, audio_response)


def test_generate_rag_questions_other_users_session_is_404(
    client, db, interview_session, interview_question, audio_response, monkeypatch
):
    from tests.conftest import OTHER_USER, _login

    client.post("/api/v1/auth/register", json=OTHER_USER)
    other_headers = {"Authorization": f"Bearer {_login(client, OTHER_USER)}"}
    _forbid_rag_calls(monkeypatch)

    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
        headers=other_headers,
    )

    assert resp.status_code == 404
    _assert_question_and_answer_intact(db, interview_question, audio_response)


def test_generate_rag_questions_gemini_failure_keeps_existing_questions(
    client, auth_headers, db, interview_session, interview_question, monkeypatch
):
    from app.core.exceptions import AIServiceError
    from app.models.interview import Question

    def _fail(**kwargs):
        raise AIServiceError("RAG question generation produced no usable questions.")

    monkeypatch.setattr(
        "app.routers.documents.rag_service.retrieve_relevant_chunks", lambda **kw: []
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.generate_rag_questions", _fail
    )

    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
        headers=auth_headers,
    )

    assert resp.status_code == 502
    db.expire_all()
    assert db.get(Question, interview_question.id) is not None


def test_generate_rag_questions_forbidden_for_recruiter(
    client, recruiter_headers, interview_session, monkeypatch
):
    _forbid_rag_calls(monkeypatch)
    resp = client.post(
        f"/api/v1/documents/interviews/{interview_session.id}/generate-rag-questions",
        json={"count": 5},
        headers=recruiter_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/v1/documents/resume/current
# ---------------------------------------------------------------------------

_DELETE = "/api/v1/documents/resume/current"


def _upload(client, headers, monkeypatch, filename, text):
    """Upload a resume whose extracted text is `text`; returns its JSON."""
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        lambda file_path, mime_type: text,
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.chunk_text", lambda text, **kw: [text]
    )
    monkeypatch.setattr(
        "app.routers.documents.rag_service.store_chunks", lambda **kw: 1
    )
    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": (filename, _make_pdf(), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _resume_rows(db, user_id):
    from app.models.documents import ResumeDocument

    db.expire_all()
    return (
        db.query(ResumeDocument)
        .filter(ResumeDocument.user_id == uuid.UUID(str(user_id)))
        .all()
    )


def _bob_headers(client):
    from tests.conftest import OTHER_USER, _login

    client.post("/api/v1/auth/register", json=OTHER_USER)
    return {"Authorization": f"Bearer {_login(client, OTHER_USER)}"}


def test_delete_resume_removes_every_version_and_file(
    client, auth_headers, registered_user, db, upload_dir, monkeypatch
):
    """Uploading a new resume keeps the old row; deleting must not let that
    older resume reappear as "current" or keep any file on disk."""
    _upload(client, auth_headers, monkeypatch, "old.pdf", "Old resume text.")
    _upload(client, auth_headers, monkeypatch, "new.pdf", "New resume text.")
    files = [r.file_path for r in _resume_rows(db, registered_user["id"])]
    assert len(files) == 2
    assert all(Path(f).exists() for f in files)

    assert client.delete(_DELETE, headers=auth_headers).status_code == 204

    assert client.get(_DELETE, headers=auth_headers).status_code == 404
    assert _resume_rows(db, registered_user["id"]) == []
    assert [f for f in files if Path(f).exists()] == []


def test_delete_resume_removes_chunks_and_leaves_other_users_alone(
    client, auth_headers, registered_user, db, upload_dir, monkeypatch
):
    from app.models.documents import DocumentChunk

    _upload(client, auth_headers, monkeypatch, "alice.pdf", "Alice resume.")
    bob = _bob_headers(client)
    bob_doc = _upload(client, bob, monkeypatch, "bob.pdf", "Bob resume.")
    bob_rows = [r for r in _resume_rows(db, bob_doc["user_id"])]
    alice_id = uuid.UUID(registered_user["id"])
    db.add(DocumentChunk(user_id=alice_id, source_type="resume", chunk_text="Alice"))
    db.commit()

    assert client.delete(_DELETE, headers=auth_headers).status_code == 204

    assert db.query(DocumentChunk).filter_by(user_id=alice_id).count() == 0
    assert client.get(_DELETE, headers=bob).json()["filename"] == "bob.pdf"
    assert len(_resume_rows(db, bob_doc["user_id"])) == 1
    assert Path(bob_rows[0].file_path).exists()


def test_delete_resume_succeeds_when_a_file_is_already_missing(
    client, auth_headers, registered_user, db, upload_dir, monkeypatch
):
    _upload(client, auth_headers, monkeypatch, "cv.pdf", "Resume text.")
    Path(_resume_rows(db, registered_user["id"])[0].file_path).unlink()

    assert client.delete(_DELETE, headers=auth_headers).status_code == 204
    assert _resume_rows(db, registered_user["id"]) == []


def test_delete_resume_without_one_is_404(client, auth_headers):
    assert client.delete(_DELETE, headers=auth_headers).status_code == 404


def test_delete_resume_requires_auth(client):
    assert client.delete(_DELETE).status_code == 401
