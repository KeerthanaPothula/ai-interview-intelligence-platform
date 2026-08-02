"""Resume upload and RAG-based question generation endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import API_V1_PREFIX
from app.core.file_validation import (
    looks_like_declared_document_type,
    sanitize_filename,
    scan_for_malware,
)
from app.core.security_logging import log_upload_rejected
from app.database import get_db
from app.models.documents import DocumentChunk, ResumeDocument
from app.models.interview import (
    InterviewSession,
    Question,
    QUESTION_SOURCE_AI_GENERATED,
)
from app.routers.auth import get_current_user
from app.schemas.documents import (
    RAGQuestionsRequest,
    RAGQuestionsResponse,
    ResumeAnalysisResponse,
    ResumeDocumentResponse,
    RAGQuestionItem,
)
from app.services import document_extraction_service, rag_service
from app.models.user import User

router = APIRouter(prefix=f"{API_V1_PREFIX}/documents", tags=["Documents"])

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/resume/upload", response_model=ResumeDocumentResponse, status_code=201)
async def upload_resume(
    request: Request,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a PDF or DOCX resume. Extracts text and stores embeddings for RAG."""
    settings = get_settings()
    max_size_bytes = settings.MAX_RESUME_UPLOAD_SIZE_MB * 1024 * 1024
    ip = _client_ip(request)

    if file.content_type not in _ALLOWED_MIME:
        log_upload_rejected(current_user.id, ip, "unsupported_mime_type")
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Upload PDF or DOCX.",
        )

    content = await file.read()
    if len(content) > max_size_bytes:
        log_upload_rejected(current_user.id, ip, "file_too_large")
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.MAX_RESUME_UPLOAD_SIZE_MB} MB)",
        )

    # Magic-byte check: Content-Type is client-supplied and spoofable.
    # Verify the file's actual leading bytes match the declared document type.
    if not looks_like_declared_document_type(content, file.content_type):
        log_upload_rejected(current_user.id, ip, "content_mismatch")
        raise HTTPException(
            status_code=422,
            detail=(
                f"File content does not match the declared type "
                f"'{file.content_type}'."
            ),
        )

    if not scan_for_malware(content):
        log_upload_rejected(current_user.id, ip, "malware_scan_failed")
        raise HTTPException(
            status_code=422,
            detail="Uploaded file failed malware scanning.",
        )

    upload_dir = Path(settings.UPLOAD_DIR) / "resumes" / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    doc_id = uuid.uuid4()
    suffix = ".pdf" if file.content_type == "application/pdf" else ".docx"
    file_path = upload_dir / f"{doc_id}{suffix}"
    file_path.write_bytes(content)

    try:
        extracted_text = document_extraction_service.extract_text(
            str(file_path), file.content_type
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to extract text: {exc}")

    # Delete previous chunks for this user (replace with new resume)
    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.user_id == current_user.id,
            DocumentChunk.source_type == "resume",
        )
    )

    doc = ResumeDocument(
        id=doc_id,
        user_id=current_user.id,
        filename=sanitize_filename(file.filename or "resume"),
        file_path=str(file_path),
        extracted_text=extracted_text,
    )
    db.add(doc)
    db.flush()

    chunks = rag_service.chunk_text(extracted_text)
    stored = rag_service.store_chunks(
        user_id=current_user.id,
        chunks=chunks,
        source_type="resume",
        resume_document_id=doc_id,
        db=db,
    )
    db.commit()

    resp = ResumeDocumentResponse.model_validate(doc)
    resp.chunk_count = stored
    return resp


@router.get("/resume/current", response_model=ResumeDocumentResponse)
def get_current_resume(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recently uploaded resume for the current user."""
    stmt = (
        select(ResumeDocument)
        .where(ResumeDocument.user_id == current_user.id)
        .order_by(ResumeDocument.created_at.desc())
        .limit(1)
    )
    doc = db.execute(stmt).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")

    chunk_count = (
        db.execute(
            select(DocumentChunk).where(DocumentChunk.resume_document_id == doc.id)
        )
        .scalars()
        .all()
    )

    resp = ResumeDocumentResponse.model_validate(doc)
    resp.chunk_count = len(chunk_count)
    return resp


@router.post(
    "/interviews/{session_id}/generate-rag-questions",
    response_model=RAGQuestionsResponse,
    status_code=201,
    tags=["Live Interviews"],
)
def generate_rag_questions(
    session_id: uuid.UUID,
    body: RAGQuestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate personalised questions using the candidate's resume context."""
    session = db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id,
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")

    relevant_chunks = rag_service.retrieve_relevant_chunks(
        query_text=f"{session.job_role} {session.job_description[:200]}",
        user_id=current_user.id,
        db=db,
        k=6,
    )

    resume_context_used = bool(relevant_chunks)

    if not relevant_chunks:
        # Fallback: generate standard questions without context
        relevant_chunks = [f"Role: {session.job_role}"]

    questions_data = rag_service.generate_rag_questions(
        job_role=session.job_role,
        job_description=session.job_description,
        relevant_chunks=relevant_chunks,
        count=body.count,
    )

    # Clear existing questions and insert RAG-generated ones
    db.execute(delete(Question).where(Question.session_id == session_id))

    for q_data in questions_data:
        q = Question(
            session_id=session_id,
            body=q_data["body"],
            sequence_order=q_data["sequence_order"],
            category=q_data.get("category"),
            source=QUESTION_SOURCE_AI_GENERATED,
        )
        db.add(q)

    db.commit()

    return RAGQuestionsResponse(
        session_id=session_id,
        questions=[
            RAGQuestionItem(
                body=q["body"],
                category=q.get("category", "behavioral"),
                sequence_order=q["sequence_order"],
            )
            for q in questions_data
        ],
        resume_context_used=resume_context_used,
        chunks_retrieved=len(relevant_chunks),
    )


@router.delete(
    "/resume/current",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the current resume",
)
def delete_current_resume(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete the current user's resume and all associated chunks."""
    stmt = (
        select(ResumeDocument)
        .where(ResumeDocument.user_id == current_user.id)
        .order_by(ResumeDocument.created_at.desc())
        .limit(1)
    )
    doc = db.execute(stmt).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")

    db.execute(
        delete(DocumentChunk).where(DocumentChunk.user_id == current_user.id)
    )
    db.delete(doc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resume/analysis", response_model=ResumeAnalysisResponse)
def analyze_resume(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResumeAnalysisResponse:
    """Analyze the current resume: ATS score, skills, suggestions."""
    import json as _json
    import re as _re

    stmt = (
        select(ResumeDocument)
        .where(ResumeDocument.user_id == current_user.id)
        .order_by(ResumeDocument.created_at.desc())
        .limit(1)
    )
    doc = db.execute(stmt).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")

    text = doc.extracted_text or ""
    word_count = len(text.split()) if text else 0

    # Call Gemini for structured resume analysis
    try:
        from app.services import gemini_service

        prompt = (
            "Analyze the following resume text and respond with ONLY valid JSON "
            "(no markdown fences, no extra text) matching this schema:\n"
            '{"ats_score": <int 0-100>, "skills": [<str>, ...], '
            '"missing_skills": [<str>, ...], "keywords": [<str>, ...], '
            '"suggestions": [<str>, ...]}\n\n'
            "Rules:\n"
            "- ats_score: estimate how well this resume would pass an ATS scan (0-100)\n"
            "- skills: up to 20 technical and soft skills found in the resume\n"
            "- missing_skills: up to 10 common skills for the role that are missing\n"
            "- keywords: up to 15 important keywords from the resume\n"
            "- suggestions: up to 5 actionable improvement suggestions\n\n"
            f"Resume text (first 3000 chars):\n{text[:3000]}"
        )
        raw = gemini_service.generate_text(prompt)
        data = _json.loads(raw)
        return ResumeAnalysisResponse(
            ats_score=int(data.get("ats_score", 70)),
            skills=data.get("skills", [])[:20],
            missing_skills=data.get("missing_skills", [])[:10],
            keywords=data.get("keywords", [])[:15],
            suggestions=data.get("suggestions", [])[:5],
            word_count=word_count,
        )
    except Exception:
        # Graceful fallback: extract skills via regex, return basic analysis
        from app.services.resume_scoring import estimate_ats_score

        common_skills = [
            "Python", "JavaScript", "TypeScript", "React", "Node.js",
            "SQL", "Git", "Docker", "AWS", "REST API",
        ]
        found = [s for s in common_skills if s.lower() in text.lower()]
        return ResumeAnalysisResponse(
            ats_score=estimate_ats_score(word_count),
            skills=found,
            missing_skills=[s for s in common_skills if s not in found][:5],
            keywords=[],
            suggestions=["Add more quantifiable achievements", "Include relevant certifications"],
            word_count=word_count,
        )
