"""Resume upload and RAG-based question generation endpoints."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.documents import DocumentChunk, ResumeDocument
from app.models.interview import InterviewSession, Question, QUESTION_SOURCE_AI_GENERATED
from app.routers.auth import get_current_user
from app.schemas.documents import (
    RAGQuestionsRequest,
    RAGQuestionsResponse,
    ResumeDocumentResponse,
    RAGQuestionItem,
)
from app.services import document_extraction_service, rag_service
from app.models.user import User

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/resume/upload", response_model=ResumeDocumentResponse, status_code=201)
async def upload_resume(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a PDF or DOCX resume. Extracts text and stores embeddings for RAG."""
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Upload PDF or DOCX.",
        )

    content = await file.read()
    if len(content) > _MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    settings = get_settings()
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
        filename=file.filename or "resume",
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

    chunk_count = db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.resume_document_id == doc.id)
    ).scalars().all()

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
