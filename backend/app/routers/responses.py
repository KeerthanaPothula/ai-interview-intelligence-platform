from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.database import get_db
from app.models.analysis import AudioResponse
from app.models.interview import Question
from app.models.user import User
from app.schemas.analysis import (
    AudioResponseResponse,
    AudioResponseStatusResponse,
    InterviewAnalysisResponse,
    TranscriptResponse,
)
from app.schemas.features import VoiceAnalysisResponse
from app.services import interview_service, processing_service, upload_service

router = APIRouter(
    prefix=API_V1_PREFIX,
    tags=["Responses"],
)


@router.post(
    "/interviews/{session_id}/responses",
    response_model=AudioResponseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an audio response for an interview question",
)
async def upload_audio(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    question_id: uuid.UUID = Form(
        ..., description="UUID of the question this recording answers."
    ),
    file: UploadFile = File(
        ..., description="Audio file (mp3, wav, webm, ogg, mp4, m4a)."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AudioResponseResponse:
    """Upload an audio recording as an answer to a specific interview question.

    Accepts multipart/form-data with:
      - file: the audio file binary
      - question_id: UUID of the question being answered

    Authentication: Bearer token required.

    Ownership (session): HTTP 404 if session_id does not exist or belongs to
    another user. HTTP 403 is never returned.

    Ownership (question): HTTP 404 if question_id does not exist or belongs
    to a different session. The question must belong to the session identified
    by session_id in the URL.

    Validation errors:
      HTTP 415 — MIME type not in allowed set, or file extension not allowed.
      HTTP 413 — file exceeds MAX_UPLOAD_SIZE_MB (default 50 MB).
      HTTP 422 — file is smaller than 1024 bytes (truncated or empty).
      HTTP 500 — filesystem write failure (disk full, permissions error).

    Orphan-file risk: save_file() writes the audio to disk first. If the
    subsequent DB insert (create_response_record) fails, the file on disk
    has no corresponding DB row — a silent orphan. This is acceptable for
    Week 2 MVP. A cleanup job (Week 5+) will reconcile DB rows with
    filesystem state. The alternative (DB row first, then file write) is
    worse: a row pointing to a missing file causes errors on every read,
    whereas an orphan file is silently ignorable.

    Response: 201 Created. The response body exposes only id, question_id,
    status, and created_at. Filesystem paths and storage metadata are never
    returned.

    Week 3 pipeline: the returned status is always 'uploaded' — this
    endpoint never runs Whisper or Gemini synchronously and never returns
    'processing', 'completed', or 'failed' itself. If
    settings.ENABLE_AUDIO_PROCESSING is True, a background task
    (processing_service.process_response) is enqueued via BackgroundTasks
    before this endpoint returns; it runs after the HTTP response has been
    sent and drives the row through the remaining lifecycle:

        uploaded -> processing -> completed
                                -> failed

    If ENABLE_AUDIO_PROCESSING is False, no background task is enqueued and
    the row remains 'uploaded' until a client calls
    POST /api/v1/responses/{response_id}/process.

    Poll GET /api/v1/responses/{response_id}/processing-status or
    GET /api/v1/responses/{id}/status to observe the four valid statuses
    ('uploaded', 'processing', 'completed', 'failed') as the pipeline runs.
    """
    # A. Enforce session ownership — HTTP 404 if missing or wrong user.
    session = interview_service.get_session_or_404(db, session_id, current_user.id)

    # B. Verify the question belongs to this session.
    #    Filters on both id and session_id in one query — a question from
    #    another session returns None and produces HTTP 404, never HTTP 403.
    question = (
        db.query(Question)
        .filter(
            Question.id == question_id,
            Question.session_id == session.id,
        )
        .first()
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")

    # C. Validate the uploaded file — reads content once, checks MIME type,
    #    extension, and size limits. Raises 413/415/422 on failure.
    content, file_size, mime_type, extension = await upload_service.validate_upload(
        file
    )

    # D. Pre-generate the response UUID so the filename and DB row share the
    #    same ID. Without this, save_file and create_response_record would
    #    each generate independent UUIDs, making file lookup by row ID impossible.
    response_id = uuid.uuid4()

    # E. Write audio bytes to disk atomically (tmp → replace).
    #    Returns a relative path: "{session_id}/{response_id}{extension}".
    settings = get_settings()
    relative_path = upload_service.save_file(
        content=content,
        session_id=session.id,
        response_id=response_id,
        extension=extension,
        upload_dir=settings.UPLOAD_DIR,
    )

    # F. Insert the DB row with status='uploaded'.
    #
    #    Orphan-file risk: if this call fails after save_file() succeeds,
    #    the audio file on disk has no corresponding DB row. Acceptable for
    #    Week 2 MVP — cleanup job will reconcile. See docstring above.
    response = upload_service.create_response_record(
        db=db,
        session=session,
        question_id=question_id,
        user_id=current_user.id,
        file_path=relative_path,
        file_size=file_size,
        mime_type=mime_type,
        response_id=response_id,
    )

    # G. Enqueue the Week 3 pipeline (Whisper transcription + Gemini
    #    evaluation) to run after this response is sent. Skipped entirely
    #    when audio processing is disabled — the row stays 'uploaded' until
    #    a client calls POST /responses/{response_id}/process (File 09).
    if settings.ENABLE_AUDIO_PROCESSING:
        background_tasks.add_task(processing_service.process_response, response.id)

    # H. Return 201 — AudioResponseResponse excludes file_path, mime_type,
    #    file_size_bytes, and user_id. No storage metadata is exposed.
    return AudioResponseResponse.model_validate(response)


@router.get(
    "/interviews/{session_id}/responses",
    response_model=list[AudioResponseResponse],
    summary="List audio responses for an interview session",
)
def list_responses(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AudioResponseResponse]:
    """Return all audio responses submitted for a session, newest first.

    Authentication: Bearer token required.
    Ownership: HTTP 404 if session not found or belongs to another user.
    Returns an empty list if no responses have been submitted yet.

    Ordered by created_at DESC — most recent upload appears first.
    Response schema excludes filesystem paths and internal storage metadata.
    """
    interview_service.get_session_or_404(db, session_id, current_user.id)

    responses = (
        db.query(AudioResponse)
        .filter(AudioResponse.session_id == session_id)
        .order_by(AudioResponse.created_at.desc())
        .all()
    )
    return [AudioResponseResponse.model_validate(r) for r in responses]


@router.get(
    "/responses/{response_id}/status",
    response_model=AudioResponseStatusResponse,
    summary="Poll the processing status of an audio response",
)
def get_response_status(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AudioResponseStatusResponse:
    """Return the current processing status of a single audio response.

    Ownership is enforced by filtering on both response_id and user_id in
    the same SQL query — a response belonging to another user returns None
    and produces HTTP 404. HTTP 403 is never returned.

    Status lifecycle (Week 3 pipeline):
      uploaded → processing → completed
                           ↘ failed

    When status == 'failed', error_message contains a human-readable reason
    set by the processing pipeline. For all other statuses, error_message
    is null.

    Authentication: Bearer token required.
    Returns HTTP 404 if the response does not exist or belongs to another user.

    Week 3 compatibility: this endpoint is the stable polling surface for the
    asynchronous transcription pipeline. The pipeline only writes to status
    and error_message — no schema change is required in Week 3.
    """
    response = (
        db.query(AudioResponse)
        .filter(
            AudioResponse.id == response_id,
            AudioResponse.user_id == current_user.id,
        )
        .first()
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Response not found.")

    return AudioResponseStatusResponse.model_validate(response)


@router.get(
    "/responses/{response_id}/transcript",
    response_model=TranscriptResponse,
    summary="Get the Whisper transcript for an audio response",
)
def get_transcript(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TranscriptResponse:
    """Return the Whisper transcript produced for one audio response.

    Ownership is enforced entirely in SQL: the WHERE clause filters on both
    AudioResponse.id and AudioResponse.user_id in the same query. A response
    that exists but belongs to another user produces the same `None` result
    — and therefore the same HTTP 404 — as a response that does not exist
    at all. HTTP 403 is never returned.

    joinedload(AudioResponse.transcript) eagerly loads the one-to-one
    transcript relationship in the same SQL statement (a single LEFT OUTER
    JOIN), avoiding a second lazy-load SELECT when response.transcript is
    accessed below.

    Authentication: Bearer token required.

    Returns HTTP 404 if response_id does not exist, belongs to another user,
    or has not yet been transcribed (transcript is None — status is
    'uploaded', 'processing', or 'failed' before Transaction 2 commits).
    """
    response = (
        db.query(AudioResponse)
        .options(joinedload(AudioResponse.transcript))
        .filter(
            AudioResponse.id == response_id,
            AudioResponse.user_id == current_user.id,
        )
        .first()
    )
    if response is None or response.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    return TranscriptResponse.model_validate(response.transcript)


@router.get(
    "/responses/{response_id}/analysis",
    response_model=InterviewAnalysisResponse,
    summary="Get the AI evaluation for an audio response",
)
def get_analysis(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InterviewAnalysisResponse:
    """Return the Gemini AI evaluation produced for one audio response.

    Ownership is enforced entirely in SQL: the WHERE clause filters on both
    AudioResponse.id and AudioResponse.user_id in the same query. A response
    that exists but belongs to another user produces the same `None` result
    — and therefore the same HTTP 404 — as a response that does not exist
    at all. HTTP 403 is never returned.

    joinedload(AudioResponse.analysis) eagerly loads the one-to-one analysis
    relationship in the same SQL statement (a single LEFT OUTER JOIN),
    avoiding a second lazy-load SELECT when response.analysis is accessed
    below.

    Authentication: Bearer token required.

    Returns HTTP 404 if response_id does not exist, belongs to another user,
    or has not yet been evaluated (analysis is None — status is 'uploaded',
    'processing', or 'failed' before Transaction 3 commits).
    """
    response = (
        db.query(AudioResponse)
        .options(joinedload(AudioResponse.analysis))
        .filter(
            AudioResponse.id == response_id,
            AudioResponse.user_id == current_user.id,
        )
        .first()
    )
    if response is None or response.analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    return InterviewAnalysisResponse.model_validate(response.analysis)


@router.get(
    "/responses/{response_id}/voice-analysis",
    response_model=VoiceAnalysisResponse,
    summary="Get the voice analytics for an audio response",
)
def get_voice_analysis(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VoiceAnalysisResponse:
    """Return the librosa voice analytics produced for one audio response.

    Returns HTTP 404 if the response does not exist, belongs to another user,
    or has not yet been processed by the voice analytics engine.
    """
    response = (
        db.query(AudioResponse)
        .options(joinedload(AudioResponse.voice_analysis))
        .filter(
            AudioResponse.id == response_id,
            AudioResponse.user_id == current_user.id,
        )
        .first()
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Response not found.")

    if response.voice_analysis is None:
        raise HTTPException(status_code=404, detail="Voice analysis not found.")

    return VoiceAnalysisResponse.model_validate(response.voice_analysis)
