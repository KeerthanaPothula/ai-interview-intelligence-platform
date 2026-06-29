from __future__ import annotations

import logging
import threading
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import SessionLocal
from app.models.analysis import (
    RESPONSE_STATUS_COMPLETED,
    RESPONSE_STATUS_FAILED,
    RESPONSE_STATUS_PROCESSING,
    RESPONSE_STATUS_UPLOADED,
    AudioResponse,
    InterviewAnalysis,
    Transcript,
)
from app.models.interview import (
    SESSION_STATUS_COMPLETED,
    InterviewSession,
    Question,
)
from app.models.features import VoiceAnalysis
from app.services import (
    evaluation_service,
    transcription_service,
    voice_analysis_service,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application-level concurrency policy.
#
# Only one Whisper transcription runs at a time, regardless of how many
# AudioResponse rows are eligible for processing. Acquired/released inside
# the worker thread spawned by _transcribe_with_timeout — see that function
# and the Timeout Review for why it is not acquired by the calling thread.
# ---------------------------------------------------------------------------
_transcription_slots = threading.Semaphore(1)


# =============================================================================
# Startup recovery
# =============================================================================


def recover_stuck_jobs(db: Session) -> int:
    """Mark jobs left in 'processing' by an unclean shutdown as 'failed'.

    Called once at application startup (see main.py lifespan handler), before
    any HTTP requests are served and before any call to process_response().
    At this point no other code path can be reading or writing AudioResponse
    rows. Recovery is a single conditional UPDATE, so its result (rowcount)
    is correct regardless of concurrency; the optional debug-only SELECT
    below (gated on logger.isEnabledFor(logging.DEBUG)) is also safe for the
    same reason — there is no concurrent writer that could change a row's
    status between it and the UPDATE.

    Rows with status 'uploaded', 'completed', or 'failed' are not touched:
      - 'uploaded': never started, still eligible for normal claiming.
      - 'completed': finished successfully before the restart.
      - 'failed': already in its terminal failure state.

    Only 'processing' rows are affected — these were claimed by a previous
    process that died (crash, deploy, OOM-kill) before reaching Transaction 3.

    Returns:
        Number of rows updated (UPDATE rowcount).
    """
    if logger.isEnabledFor(logging.DEBUG):
        stuck_ids = [
            row[0]
            for row in db.query(AudioResponse.id)
            .filter(AudioResponse.status == RESPONSE_STATUS_PROCESSING)
            .all()
        ]
        logger.debug("Startup recovery: response IDs to recover: %s", stuck_ids)

    rowcount = (
        db.query(AudioResponse)
        .filter(AudioResponse.status == RESPONSE_STATUS_PROCESSING)
        .update(
            {
                "status": RESPONSE_STATUS_FAILED,
                "error_message": "Server restart interrupted processing",
            },
            synchronize_session=False,
        )
    )
    db.commit()

    if rowcount:
        logger.info("Startup recovery: marked %d job(s) as failed", rowcount)
    else:
        logger.info("Startup recovery: no stuck jobs found")

    return rowcount


# =============================================================================
# Atomic job claim
# =============================================================================


def claim_response(db: Session, response_id: uuid.UUID) -> bool:
    """Atomically transition one AudioResponse to 'processing' (uncommitted).

    Issues a single conditional UPDATE:

        UPDATE audio_responses
        SET status='processing',
            processing_started_at=NOW(),
            error_message=NULL
        WHERE id=:response_id
          AND status IN ('uploaded', 'failed')

    There is deliberately no SELECT before this UPDATE. A SELECT-then-UPDATE
    pattern would create a TOCTOU (time-of-check-to-time-of-use) race: two
    concurrent callers (e.g. the user double-clicks "Process", or a retry
    fires while the original BackgroundTask is still running) could both
    SELECT the row while it is still 'uploaded', both see it as eligible,
    and both proceed to run the full pipeline — duplicating Whisper and
    Gemini calls and racing to write the Transcript/InterviewAnalysis rows
    (which would violate the UNIQUE(audio_response_id) constraints on both
    tables, but only after wasting a full Whisper transcription).

    The conditional UPDATE closes this race at the database level: an UPDATE
    takes a row-level lock on any row it matches for the remainder of the
    transaction. If two callers issue this UPDATE concurrently for the same
    response_id, the database serializes them — the second caller's UPDATE
    blocks until the first caller's transaction commits or rolls back. When
    it unblocks, it re-evaluates the WHERE clause against the now-current
    row: if the first caller committed 'processing', the second caller's
    WHERE clause no longer matches (rowcount 0); if the first caller rolled
    back instead, the row is still 'uploaded'/'failed' and the second
    caller's UPDATE matches and proceeds (rowcount 1). Exactly one caller's
    transaction ever commits this row as 'processing'.

    This function does NOT commit. The caller owns the transaction boundary
    and is responsible for either committing this UPDATE (together with
    whatever else the caller does in the same transaction) or letting
    db.close() roll it back — see _claim_and_load_context for why this
    matters.

    Returns:
        True  if this call's UPDATE matched the row (rowcount == 1) — the
              caller should proceed and eventually commit.
        False if rowcount == 0 — another caller's committed claim already
              holds this row, the row does not exist, or it is already
              'processing' or 'completed'. The caller must not proceed, and
              there is nothing for it to commit or roll back.
    """
    rowcount = (
        db.query(AudioResponse)
        .filter(
            AudioResponse.id == response_id,
            AudioResponse.status.in_(
                [RESPONSE_STATUS_UPLOADED, RESPONSE_STATUS_FAILED]
            ),
        )
        .update(
            {
                "status": RESPONSE_STATUS_PROCESSING,
                "processing_started_at": func.now(),
                "error_message": None,
            },
            synchronize_session=False,
        )
    )

    if rowcount == 0:
        logger.info(
            "Claim failed for response_id=%s (not eligible or not found)",
            response_id,
        )
        return False

    logger.info("Claim succeeded for response_id=%s", response_id)
    return True


# =============================================================================
# Transaction 1: claim + load context
# =============================================================================


def _claim_and_load_context(
    response_id: uuid.UUID,
) -> tuple[str, uuid.UUID, str, str, str, dict | None] | None:
    """Claim the job and load everything the pipeline needs, in one transaction.

    This is "Transaction 1". claim_response()'s UPDATE and the joinedload
    SELECT below run on the same SessionLocal() and are committed together by
    the single db.commit() near the end of this function. claim_response()
    itself does not commit (see its docstring) — this function owns the
    Transaction 1 boundary: claim, load, copy values, commit, close.

    Why claim and load must commit together:

        If claim_response() committed on its own, a row could become durably
        'processing' even though the joinedload SELECT below had not yet
        succeeded. Any failure after that independent commit — an unexpected
        exception from the SELECT, or the process being killed before
        _mark_failed() could run — would leave the row stuck at 'processing'
        with no code path still running for it. Such a row is only ever
        recovered by recover_stuck_jobs() at the next application startup.

        Committing the claim and the load together closes this gap. If the
        SELECT below raises, this function's `finally: db.close()` rolls
        back the still-uncommitted claim UPDATE — Session.close() without a
        prior commit() discards the pending transaction. The row reverts to
        its pre-claim status ('uploaded' or 'failed'), which is immediately
        re-claimable by the next call to claim_response(), with no server
        restart required. The same applies if the process is killed between
        the UPDATE and this function's commit(): the database discards the
        uncommitted UPDATE when the connection is lost.

        This narrows the set of failures that can leave a row stuck at
        'processing' — i.e. requiring recover_stuck_jobs() — to failures
        that occur AFTER this function's commit(): during Whisper
        transcription, Transaction 2, evaluation, or Transaction 3. The
        "claimed but context never loaded" failure mode is eliminated as a
        source of stuck jobs entirely.

    The SELECT uses:

        joinedload(AudioResponse.question).joinedload(Question.session)

    This produces a single SQL statement (AudioResponse LEFT OUTER JOIN
    questions LEFT OUTER JOIN interview_sessions) and populates
    response.question and response.question.session in the same round trip.

    Why this matters: every value the rest of the pipeline needs —
    file_path, session_id, the question body, job_role, job_description —
    is read out into plain Python locals (a tuple of str/UUID) BEFORE the
    `finally: db.close()` runs. After db.close(), `response` and its related
    objects become detached SQLAlchemy instances. Accessing an attribute on a
    detached instance that was not already loaded into __dict__ raises
    DetachedInstanceError, because SQLAlchemy would normally lazy-load it via
    a SELECT on `response`'s session — and that session is closed.

    Because joinedload eagerly populated `response.question` and
    `response.question.session` in the original SELECT, every attribute
    accessed below (.file_path, .session_id, .question.body,
    .question.session.job_role, .question.session.job_description) is
    already present in the relevant object's __dict__. No lazy load is
    triggered, so no DetachedInstanceError occurs even though we read these
    attributes before committing and closing the session.

    Once this function returns, the caller holds only plain Python values —
    it must never receive or touch `response` itself.

    Idempotent retries — joinedload(AudioResponse.transcript):

        This additionally eager-loads any Transcript row already committed
        for this response_id by a prior, partially-failed attempt (claimable
        again because that attempt left status='failed' — see claim_response).
        If present, its fields are copied into a plain dict for the same
        detached-instance reason as the rest of this context.

        process_response uses this dict to skip Whisper transcription and
        Transaction 2 entirely on retry, going straight to evaluation with
        the previously-transcribed text. This guarantees Transaction 2 — the
        single INSERT into transcripts — runs at most once per response_id,
        so a retry can never violate uq_transcripts_audio_response_id.

    Returns:
        None if the claim failed (rowcount 0 — nothing was changed, nothing
        to commit, not a failure).
        Otherwise (file_path, session_id, question_body, job_role,
        job_description, existing_transcript) — committed and safe to use
        after db.close(). existing_transcript is None on a first attempt, or
        a dict with keys id/text/language/duration_seconds/word_count if a
        Transcript from a prior attempt already exists.
    """
    db = SessionLocal()
    try:
        if not claim_response(db, response_id):
            return None

        response = (
            db.query(AudioResponse)
            .options(
                joinedload(AudioResponse.question).joinedload(Question.session),
                joinedload(AudioResponse.transcript),
            )
            .filter(AudioResponse.id == response_id)
            .one()
        )

        existing_transcript = (
            {
                "id": response.transcript.id,
                "text": response.transcript.text,
                "language": response.transcript.language,
                "duration_seconds": response.transcript.duration_seconds,
                "word_count": response.transcript.word_count,
            }
            if response.transcript is not None
            else None
        )

        context = (
            response.file_path,
            response.session_id,
            response.question.body,
            response.question.session.job_role,
            response.question.session.job_description,
            existing_transcript,
        )

        db.commit()
        return context
    finally:
        db.close()


# =============================================================================
# Whisper transcription with timeout + semaphore
# =============================================================================


def _transcribe_with_timeout(file_path: str, timeout_seconds: int) -> dict:
    """Run transcribe_audio() in a worker thread, bounded by timeout_seconds.

    Semaphore behavior:
        _transcription_slots.acquire() / .release() happen INSIDE _worker,
        i.e. in the spawned thread — not in the calling thread, and not
        wrapped around thread.join() below.

        This is deliberate. Python cannot forcibly terminate a running
        thread. If thread.join(timeout=...) times out, _worker is still
        running on its own thread; thread.is_alive() is True. If the
        semaphore had instead been acquired by the calling thread before
        thread.start() and released in a `finally` after `join`, that
        release would happen while _worker is still mid-transcription —
        immediately freeing the slot for a second job to start a second
        Whisper inference concurrently with the orphaned one. That is
        exactly the outcome Semaphore(1) exists to prevent (see
        transcription_service Thread Safety Review: CPU saturation,
        unbounded memory, unpredictable latency).

        By acquiring/releasing inside _worker itself, the slot remains held
        for as long as the orphaned thread is actually running, regardless
        of whether the calling thread gave up waiting. The slot is only
        released when _worker's `finally` runs — i.e. when transcription
        truly finishes (successfully or with an error). The next queued job
        cannot start its own transcription until that happens, preserving
        the "one Whisper inference at a time" invariant even across timeouts.

    Timeout handling:
        thread.join(timeout=timeout_seconds) blocks the calling thread for at
        most timeout_seconds. If the worker has not finished by then,
        thread.is_alive() is True and this function raises
        RuntimeError("Whisper transcription timed out."). The caller
        (process_response) catches this in its outer except block and marks
        the AudioResponse 'failed' with this message. The worker thread is
        abandoned (daemon=True so it cannot block process shutdown) and its
        eventual result, if any, is discarded.

    Raises:
        RuntimeError: timeout elapsed before the worker finished.
        Exception: whatever transcribe_audio() raised (FileNotFoundError,
                   RuntimeError for ffmpeg/empty-transcript, etc.) — re-raised
                   unchanged so the caller's error_message reflects the real
                   cause.
    """
    result_box: dict = {}
    error_box: dict = {}

    def _worker() -> None:
        _transcription_slots.acquire()
        try:
            result_box["value"] = transcription_service.transcribe_audio(file_path)
        except Exception as exc:  # noqa: BLE001 - re-raised in calling thread
            error_box["error"] = exc
        finally:
            _transcription_slots.release()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise RuntimeError("Whisper transcription timed out.")

    if "error" in error_box:
        raise error_box["error"]

    return result_box["value"]


# =============================================================================
# Failure handler
# =============================================================================


def _mark_failed(response_id: uuid.UUID, error_message: str) -> None:
    """Mark an AudioResponse as 'failed', unless it is already 'completed'.

    Issues:

        UPDATE audio_responses
        SET status='failed',
            error_message=:error_message,
            processing_completed_at=NOW()
        WHERE id=:response_id
          AND status != 'completed'

    Race condition prevented by `WHERE status != 'completed'`:

        process_response runs Transaction 2 (insert Transcript) and
        Transaction 3 (insert InterviewAnalysis, set status='completed') as
        separate, non-atomic transactions. It is possible — though only
        under pathological conditions such as a second concurrent call to
        process_response for the same response_id that was somehow not
        rejected by claim_response — for Transaction 3 to commit
        ('completed') and for this failure handler to then run afterward
        for a stale exception from a different code path.

        Without the WHERE guard, this UPDATE would unconditionally overwrite
        status='completed' back to 'failed', discarding a successful
        analysis because of an unrelated, late-arriving error. The
        `status != 'completed'` guard makes this UPDATE a no-op (rowcount 0)
        if the job already finished successfully — a completed result is
        never downgraded.

        This is the same defensive pattern as claim_response's WHERE clause:
        the database, not application logic, is the source of truth for
        "did this row already reach a terminal success state".
    """
    db = SessionLocal()
    try:
        db.query(AudioResponse).filter(
            AudioResponse.id == response_id,
            AudioResponse.status != RESPONSE_STATUS_COMPLETED,
        ).update(
            {
                "status": RESPONSE_STATUS_FAILED,
                "error_message": error_message,
                "processing_completed_at": func.now(),
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


# =============================================================================
# Voice analytics helper
# =============================================================================


def _try_insert_voice_analysis(
    *,
    response_id: uuid.UUID,
    file_path: str,
    transcript_text: str,
    word_count: int,
    duration_seconds: int | None,
) -> None:
    """Run voice analytics and persist the result — best-effort, never raises.

    Skipped if a VoiceAnalysis row already exists for this response_id
    (idempotent retry: prior attempt already completed this step).
    Any exception (librosa missing, corrupt audio, DB error) is caught,
    logged as a warning, and swallowed so the main pipeline continues.
    """
    db = SessionLocal()
    try:
        existing = (
            db.query(VoiceAnalysis)
            .filter(VoiceAnalysis.audio_response_id == response_id)
            .first()
        )
        if existing is not None:
            logger.info(
                "VoiceAnalysis already exists, skipping: response_id=%s", response_id
            )
            return
    finally:
        db.close()

    try:
        metrics = voice_analysis_service.analyze_audio(
            file_path=file_path,
            transcript_text=transcript_text,
            word_count=word_count,
            duration_seconds=duration_seconds,
        )
    except Exception as exc:
        logger.warning(
            "Voice analysis failed for response_id=%s (non-fatal): %s",
            response_id,
            exc,
        )
        return

    db = SessionLocal()
    try:
        voice_row = VoiceAnalysis(
            id=uuid.uuid4(),
            audio_response_id=response_id,
            speaking_rate=metrics["speaking_rate"],
            average_pause_duration=metrics["average_pause_duration"],
            total_pause_time=metrics["total_pause_time"],
            long_pause_count=metrics["long_pause_count"],
            filler_word_count=metrics["filler_word_count"],
            energy_consistency=metrics["energy_consistency"],
            confidence_score=metrics["confidence_score"],
        )
        db.add(voice_row)
        db.commit()
        logger.info(
            "VoiceAnalysis created: response_id=%s, confidence=%d",
            response_id,
            metrics["confidence_score"],
        )
    except Exception as exc:
        logger.warning(
            "Failed to persist VoiceAnalysis for response_id=%s (non-fatal): %s",
            response_id,
            exc,
        )
    finally:
        db.close()


# =============================================================================
# Main entrypoint
# =============================================================================


def process_response(response_id: uuid.UUID) -> None:
    """Run the full Whisper + Gemini pipeline for one AudioResponse.

    Called from a FastAPI BackgroundTask (File 10) or directly (File 09's
    POST /process endpoint). Safe to call multiple times for the same
    response_id — claim_response ensures only one call proceeds past
    Transaction 1.

    Pipeline (see class-level docstrings on each helper for transaction
    boundary details):

        Transaction 1  _claim_and_load_context()
                       claim job, load AudioResponse+Question+Session+
                       Transcript via joinedload, copy to locals, commit,
                       close session.
                       Returns None (not claimable) -> early return, no error.

        (no DB)        _transcribe_with_timeout()
                       Whisper transcription, semaphore-gated, timeout-bounded.
                       SKIPPED if Transaction 1 found an existing Transcript
                       for this response_id (see "Idempotent retries" below).

        Transaction 2  insert Transcript row, commit, close session.
                       SKIPPED for the same reason — runs at most once per
                       response_id.

        (no DB)        evaluation_service.generate_evaluation()
                       Gemini call with truncated transcript text.

        Transaction 3  insert InterviewAnalysis row, set AudioResponse
                       status='completed' + processing_completed_at,
                       check session completion, commit, close session.

    Idempotent retries:
        If a prior attempt completed Transaction 2 (Transcript inserted) and
        then failed during evaluation or Transaction 3, that Transcript row
        is still present when this response is retried (status='failed' is
        re-claimable — see claim_response). _claim_and_load_context detects
        it and returns its fields as `existing_transcript`. This run then
        skips Whisper and Transaction 2 entirely and proceeds directly to
        evaluation using the previously-transcribed text. Transaction 2 is
        therefore guaranteed to execute at most once per response_id, so a
        retry can never violate uq_transcripts_audio_response_id.

    Any exception raised after a successful claim — from transcription,
    Transaction 2, evaluation, or Transaction 3 — is caught by the outer
    except block, logged, and reported via _mark_failed(), which sets
    status='failed' and error_message=str(exc) (guarded by
    `WHERE status != 'completed'`, see _mark_failed docstring).

    Transcript text is never included in any log message in this function.
    """
    settings = get_settings()

    # ------------------------------------------------------------------
    # Transaction 1
    # ------------------------------------------------------------------
    try:
        context = _claim_and_load_context(response_id)
    except Exception as exc:
        logger.error(
            "process_response: failed during claim/load for response_id=%s: %s",
            response_id,
            exc,
        )
        _mark_failed(response_id, str(exc))
        return

    if context is None:
        # claim_response already logged the reason. Not an error: another
        # worker has this job, or it is not in a claimable state.
        return

    (
        file_path_rel,
        session_id,
        question_text,
        job_role,
        job_description,
        existing_transcript,
    ) = context

    logger.info("process_response: pipeline started for response_id=%s", response_id)

    try:
        # Compute full path once — needed for both Whisper and voice analytics.
        full_path = str(Path(settings.UPLOAD_DIR) / file_path_rel)

        if existing_transcript is not None:
            # ------------------------------------------------------------
            # Idempotent retry path.
            #
            # A Transcript already exists for this response_id — Transaction
            # 2 committed on a prior attempt that subsequently failed during
            # evaluation or Transaction 3 (see _mark_failed, which leaves
            # status='failed' and re-claimable without touching transcripts).
            # Reuse it verbatim: do not call Whisper again, and do not insert
            # a second Transcript row, which would violate
            # uq_transcripts_audio_response_id.
            # ------------------------------------------------------------
            transcript_id = existing_transcript["id"]
            transcription_result = {
                "text": existing_transcript["text"],
                "language": existing_transcript["language"],
                "duration_seconds": existing_transcript["duration_seconds"],
                "word_count": existing_transcript["word_count"],
            }
            logger.info(
                "Transcript already exists, skipping transcription: "
                "response_id=%s, transcript_id=%s",
                response_id,
                transcript_id,
            )
        else:
            # ------------------------------------------------------------
            # Whisper transcription (no DB session held)
            # ------------------------------------------------------------

            logger.info("Transcription started: response_id=%s", response_id)
            transcription_result = _transcribe_with_timeout(
                full_path, settings.WHISPER_TIMEOUT_SECONDS
            )
            logger.info(
                "Transcription complete: response_id=%s, words=%d, duration=%ss, language=%s",
                response_id,
                transcription_result["word_count"],
                transcription_result["duration_seconds"],
                transcription_result["language"],
            )

            # ------------------------------------------------------------
            # Transaction 2: insert Transcript
            #
            # transcript_id is generated here, in Python, before the INSERT.
            # The ORM default (uuid.uuid4 on the model) would also generate it,
            # but generating it explicitly lets this function pass transcript_id
            # to InterviewAnalysis in Transaction 3 without re-reading it from
            # the (by then closed and detached) Transcript object — avoiding
            # the same DetachedInstanceError class of bug described in
            # _claim_and_load_context.
            #
            # Reached only when existing_transcript is None, i.e. no
            # Transcript row exists yet for this response_id — so this
            # INSERT runs at most once per response_id. See "Idempotent
            # retries" above.
            # ------------------------------------------------------------
            transcript_id = uuid.uuid4()
            db = SessionLocal()
            try:
                transcript = Transcript(
                    id=transcript_id,
                    audio_response_id=response_id,
                    text=transcription_result["text"],
                    language=transcription_result["language"],
                    duration_seconds=transcription_result["duration_seconds"],
                    word_count=transcription_result["word_count"],
                )
                db.add(transcript)
                db.commit()
            finally:
                db.close()

            logger.info(
                "Transcript created: response_id=%s, transcript_id=%s",
                response_id,
                transcript_id,
            )

        # ------------------------------------------------------------
        # Voice analytics (no DB session held) — best-effort.
        # Runs after Whisper so word_count/duration are available.
        # Failures are logged and swallowed; they must not abort the
        # evaluation pipeline.
        # ------------------------------------------------------------
        _try_insert_voice_analysis(
            response_id=response_id,
            file_path=full_path,
            transcript_text=transcription_result["text"],
            word_count=transcription_result["word_count"],
            duration_seconds=transcription_result["duration_seconds"],
        )

        # ------------------------------------------------------------
        # Evaluation (no DB session held)
        #
        # The full transcript is stored in Transcript.text (above) and is
        # never modified. Only the copy sent to Gemini is truncated.
        # ------------------------------------------------------------
        full_text = transcription_result["text"]
        if len(full_text) > settings.MAX_TRANSCRIPT_CHARS:
            logger.info(
                "Transcript truncated for evaluation: response_id=%s, %d -> %d chars",
                response_id,
                len(full_text),
                settings.MAX_TRANSCRIPT_CHARS,
            )
        evaluation_input = full_text[: settings.MAX_TRANSCRIPT_CHARS]

        logger.info("Evaluation started: response_id=%s", response_id)
        evaluation_result = evaluation_service.generate_evaluation(
            transcript_text=evaluation_input,
            question=question_text,
            job_role=job_role,
            job_description=job_description,
        )
        logger.info("Evaluation complete: response_id=%s", response_id)

        # ------------------------------------------------------------
        # Transaction 3: insert InterviewAnalysis, complete response,
        # check session completion
        #
        # analysis_id is pre-generated for the same reason as transcript_id
        # above: this function never needs to read .id back off an ORM
        # object after commit.
        #
        # Score floats from evaluation_service (already round(v, 1)) are
        # converted via Decimal(str(v)) — NOT Decimal(v) — so the Decimal
        # constructor sees the same digits that round() produced (e.g.
        # Decimal("7.5")) rather than the binary float's exact value
        # (e.g. Decimal("7.4999999999999991118...")).
        # ------------------------------------------------------------
        analysis_id = uuid.uuid4()
        db = SessionLocal()
        try:
            analysis = InterviewAnalysis(
                id=analysis_id,
                audio_response_id=response_id,
                transcript_id=transcript_id,
                overall_score=Decimal(str(evaluation_result["overall_score"])),
                communication_score=Decimal(
                    str(evaluation_result["communication_score"])
                ),
                technical_score=Decimal(str(evaluation_result["technical_score"])),
                problem_solving_score=Decimal(
                    str(evaluation_result["problem_solving_score"])
                ),
                confidence_score=Decimal(str(evaluation_result["confidence_score"])),
                strengths=evaluation_result["strengths"],
                weaknesses=evaluation_result["weaknesses"],
                detailed_feedback=evaluation_result["detailed_feedback"],
                model_used=evaluation_result["model_used"],
            )
            db.add(analysis)

            db.query(AudioResponse).filter(AudioResponse.id == response_id).update(
                {
                    "status": RESPONSE_STATUS_COMPLETED,
                    "processing_completed_at": func.now(),
                },
                synchronize_session=False,
            )

            # Session completion check.
            #
            # A session is complete only when every QUESTION has a completed
            # response, not merely when every EXISTING AudioResponse row is
            # 'completed'. A session with 5 questions and only 1 (completed)
            # AudioResponse must stay 'in_progress' — 4 questions are still
            # unanswered. Comparing COUNT(AudioResponse WHERE status='completed')
            # against COUNT(Question) for the session correctly accounts for
            # questions that have no AudioResponse row at all yet.
            #
            # A permanently-failed response holds the session open until it is
            # reprocessed (status -> 'failed' is re-claimable by claim_response)
            # and eventually reaches 'completed' — it is never counted here.
            # Both counts are aggregate SQL queries; no rows are loaded into
            # memory.
            completed_response_count = (
                db.query(AudioResponse)
                .filter(
                    AudioResponse.session_id == session_id,
                    AudioResponse.status == RESPONSE_STATUS_COMPLETED,
                )
                .count()
            )

            total_question_count = (
                db.query(Question).filter(Question.session_id == session_id).count()
            )

            if completed_response_count == total_question_count:
                db.query(InterviewSession).filter(
                    InterviewSession.id == session_id
                ).update(
                    {"status": SESSION_STATUS_COMPLETED},
                    synchronize_session=False,
                )
                logger.info("Session completed: session_id=%s", session_id)

            db.commit()
        finally:
            db.close()

        logger.info(
            "Analysis created: response_id=%s, analysis_id=%s",
            response_id,
            analysis_id,
        )
        logger.info(
            "process_response: pipeline completed for response_id=%s", response_id
        )

    except Exception as exc:
        logger.error(
            "process_response: job failed for response_id=%s: %s", response_id, exc
        )
        _mark_failed(response_id, str(exc))
