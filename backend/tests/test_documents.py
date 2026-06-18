"""Tests for document upload and RAG question generation endpoints."""

import io
import json
import uuid


_EXTRACTED_TEXT = "Experienced Python engineer with 5 years of FastAPI and PostgreSQL expertise."
_RAG_QUESTIONS = [
    {"body": "Tell me about your FastAPI experience.", "category": "technical", "sequence_order": 1},
    {"body": "How have you optimised PostgreSQL queries?", "category": "technical", "sequence_order": 2},
    {"body": "Describe a challenging project.", "category": "behavioral", "sequence_order": 3},
    {"body": "How do you handle deadlines?", "category": "situational", "sequence_order": 4},
    {"body": "Walk me through a system you designed.", "category": "technical", "sequence_order": 5},
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
    monkeypatch.setattr("app.routers.documents.rag_service.chunk_text", lambda text, **kw: [text])
    monkeypatch.setattr("app.routers.documents.rag_service.store_chunks", lambda **kw: 1)

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
    monkeypatch.setattr("app.routers.documents.rag_service.chunk_text", lambda text, **kw: [text])
    monkeypatch.setattr("app.routers.documents.rag_service.store_chunks", lambda **kw: 1)
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
