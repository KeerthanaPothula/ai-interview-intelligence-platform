from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.database import get_db
from app.models.analysis import (
    RESPONSE_STATUS_COMPLETED,
    RESPONSE_STATUS_PROCESSING,
    AudioResponse,
)
from app.models.user import User
from app.schemas.analysis import ProcessingStatusResponse, ProcessResponseRequest
from app.services import processing_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=API_V1_PREFIX,
    tags=["processing"],
)

# Statuses for which a new processing job must NOT be enqueued.
# See the "No reprocessing policy" section of trigger_processing()'s
# docstring for why these two — and only these two — are excluded.
_NOT_ENQUEUABLE: tuple[str, str] = (
    RESPONSE_STATUS_PROCESSING,
    RESPONSE_STATUS_COMPLETED,
)


# =============================================================================
# Shared helpers
# =============================================================================


def _get_owned_response_or_404(
    db: Session, response_id: uuid.UUID, user_id: uuid.UUID
) -> AudioResponse:
    """Load an AudioResponse scoped to its owner, with children eager-loaded.

    Ownership is enforced entirely in SQL: the WHERE clause filters on both
    AudioResponse.id and AudioResponse.user_id in a single query. A row that
    exists but belongs to a different user produces exactly the same `None`
    result — and therefore exactly the same HTTP 404 — as a row that does
    not exist at all. This function never loads a row by id alone and then
    compares user_id in Python; see the Security Review for why that
    distinction matters.

    joinedload(AudioResponse.transcript) and joinedload(AudioResponse.analysis)
    eagerly populate both one-to-one child relationships in the same SQL
    statement (two LEFT OUTER JOINs added to the base query). Without this,
    accessing response.transcript / response.analysis in
    _to_status_response() would each trigger a separate lazy-load SELECT —
    an N+1 pattern across the two relationships for every call to this
    endpoint.

    Raises:
        HTTPException 404: no row matches both response_id and user_id.
    """
    response = (
        db.query(AudioResponse)
        .options(
            joinedload(AudioResponse.transcript),
            joinedload(AudioResponse.analysis),
        )
        .filter(
            AudioResponse.id == response_id,
            AudioResponse.user_id == user_id,
        )
        .first()
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Response not found.")
    return response


def _to_status_response(response: AudioResponse) -> ProcessingStatusResponse:
    """Build a ProcessingStatusResponse from a loaded AudioResponse.

    Assumes response.transcript and response.analysis are already populated
    (via joinedload in _get_owned_response_or_404) — accessing them here
    triggers no additional queries.
    """
    return ProcessingStatusResponse(
        response_id=response.id,
        status=response.status,
        transcript_id=response.transcript.id if response.transcript else None,
        analysis_id=response.analysis.id if response.analysis else None,
        error_message=response.error_message,
    )


# =============================================================================
# POST /responses/{response_id}/process
# =============================================================================


@router.post(
    "/responses/{response_id}/process",
    response_model=ProcessingStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger AI processing for an audio response",
)
def trigger_processing(
    response_id: uuid.UUID,
    body: ProcessResponseRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessingStatusResponse:
    """Manually enqueue the Whisper + Gemini pipeline for one audio response.

    Authentication: Bearer token required (get_current_user).

    Request body consistency:
        ProcessResponseRequest carries response_id in the body in addition
        to the URL path parameter (see that schema's docstring). This
        endpoint requires the two to match — a mismatch is a malformed
        request (HTTP 422) and is rejected before any database access,
        independent of ownership.

    Ownership: enforced in SQL by _get_owned_response_or_404 — HTTP 404 if
    response_id does not exist or belongs to a different user. HTTP 403 is
    never returned (see Security Review).

    Processing-enabled gate: if settings.ENABLE_AUDIO_PROCESSING is False,
    returns HTTP 503 "Audio processing is disabled." This check runs after
    the ownership check, so a request for a response the caller does not own
    still receives 404 regardless of the global gate state.

    No reprocessing policy:
        - status == 'processing' or 'completed': no new background task is
          enqueued. The current ProcessingStatusResponse is returned as-is.
        - status == 'uploaded' or 'failed': a background task is enqueued.

        Why: processing_service.claim_response() (File 08) only transitions
        rows whose status is 'uploaded' or 'failed' — its UPDATE has
        `WHERE status IN ('uploaded', 'failed')`. Enqueueing
        process_response() for a row already at 'processing' or 'completed'
        would therefore always be claimed-and-rejected (rowcount 0) the
        moment the background task ran: zero Whisper calls, zero Gemini
        calls, zero DB writes beyond one no-op UPDATE attempt. The check
        here is a request-time short-circuit for that guaranteed-no-op case
        — it avoids scheduling pointless background work and avoids
        returning a 202 that implies "a new run was just started" when no
        new run will actually occur. The actual mutual-exclusion guarantee
        does not depend on this check; it is enforced by claim_response()'s
        atomic conditional UPDATE regardless (see Concurrency Review).

    Trigger behavior: processing always runs via BackgroundTasks —
    background_tasks.add_task(processing_service.process_response,
    response.id) — never synchronously. The HTTP response is returned
    immediately; the pipeline (Whisper transcription, Transaction 2,
    Gemini evaluation, Transaction 3) runs after the response has been sent.

    Response: the row is reloaded via _get_owned_response_or_404 after
    add_task() so the returned ProcessingStatusResponse always reflects a
    fresh read of the committed database state, not a value cached from
    earlier in this request.

    Transcript text is never logged by this endpoint.
    """
    if body.response_id != response_id:
        raise HTTPException(
            status_code=422,
            detail="response_id in request body must match the URL path.",
        )

    response = _get_owned_response_or_404(db, response_id, current_user.id)

    settings = get_settings()
    if not settings.ENABLE_AUDIO_PROCESSING:
        logger.info(
            "Manual processing trigger rejected (processing disabled): "
            "response_id=%s, user_id=%s",
            response_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=503,
            detail="Audio processing is disabled.",
        )

    if response.status in _NOT_ENQUEUABLE:
        logger.info(
            "Manual processing trigger skipped: response_id=%s, user_id=%s, status=%s",
            response_id,
            current_user.id,
            response.status,
        )
        return _to_status_response(response)

    logger.info(
        "Manual processing trigger: response_id=%s, user_id=%s, status=%s",
        response_id,
        current_user.id,
        response.status,
    )
    background_tasks.add_task(processing_service.process_response, response.id)

    response = _get_owned_response_or_404(db, response_id, current_user.id)
    return _to_status_response(response)


# =============================================================================
# GET /responses/{response_id}/processing-status
# =============================================================================


@router.get(
    "/responses/{response_id}/processing-status",
    response_model=ProcessingStatusResponse,
    summary="Get the current processing status of an audio response",
)
def get_processing_status(
    response_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProcessingStatusResponse:
    """Return the current pipeline status for one audio response.

    Authentication: Bearer token required (get_current_user).

    Ownership: enforced in SQL by _get_owned_response_or_404 — HTTP 404 if
    response_id does not exist or belongs to a different user. HTTP 403 is
    never returned (see Security Review).

    status is one of 'uploaded', 'processing', 'completed', 'failed'
    (ResponseStatus, app.schemas.analysis). transcript_id and analysis_id
    are populated as soon as Transaction 2 / Transaction 3 (File 08) commit
    — a client may observe transcript_id set while status is still
    'processing' (after Transaction 2 but before Transaction 3) or while
    status is 'failed' (if Transaction 2 committed but evaluation
    subsequently failed). error_message is non-null only when
    status == 'failed'.

    This endpoint performs no writes and does not interact with
    claim_response() or process_response().

    Transcript text is never logged by this endpoint.
    """
    response = _get_owned_response_or_404(db, response_id, current_user.id)

    logger.info(
        "Processing status lookup: response_id=%s, user_id=%s, status=%s",
        response_id,
        current_user.id,
        response.status,
    )
    return _to_status_response(response)
