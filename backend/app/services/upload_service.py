from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.analysis import AudioResponse, RESPONSE_STATUS_UPLOADED
from app.models.interview import (
    InterviewSession,
    SESSION_STATUS_DRAFT,
    SESSION_STATUS_IN_PROGRESS,
)

# ---------------------------------------------------------------------------
# Allowed MIME types and extensions
#
# MIME type comes from the Content-Type header in the multipart request — it
# is client-supplied and could be spoofed. Extension comes from the filename.
# Both are validated as independent filters. A file named "audio.webm" with
# Content-Type: text/html fails the MIME check before extension is evaluated.
# ---------------------------------------------------------------------------

_ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "audio/mpeg",
        "audio/wav",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
        "video/webm",
        "video/mp4",
    }
)

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp3",
        ".wav",
        ".webm",
        ".ogg",
        ".mp4",
        ".m4a",
    }
)

# Files under 1 KB are almost certainly truncated or empty — not usable audio.
_MIN_FILE_BYTES: int = 1024


async def validate_upload(file: UploadFile) -> tuple[bytes, int, str, str]:
    """Read and validate an uploaded audio file.

    Performs all checks in this order:
      1. filename must not be None (multipart form must include a filename)
      2. filename must have an extension
      3. MIME type (Content-Type header) must be in the allowed set
      4. extension must be in the allowed set
      5. read content exactly once
      6. file size must not exceed MAX_UPLOAD_SIZE_MB (HTTP 413)
      7. file size must be at least 1024 bytes (HTTP 422)

    Returns:
        Tuple of (content_bytes, file_size_bytes, mime_type, extension).

    Why the file is read exactly once:
        UploadFile wraps a SpooledTemporaryFile. After read(), the cursor is
        at EOF — a second read() returns b"". Seeking requires an extra
        async I/O call. Reading once into bytes makes the content available
        for both size validation and the save_file write with zero extra I/O.

    Why validate MIME type before reading:
        MIME type and extension checks are cheap (dict lookup). Reading the
        full file into memory is expensive (up to MAX_UPLOAD_SIZE_MB bytes).
        Rejecting invalid MIME types and extensions before read() avoids
        loading multi-megabyte payloads for clearly invalid requests.
    """
    if not file.filename:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file must have a filename.",
        )

    _, raw_ext = os.path.splitext(file.filename)
    extension = raw_ext.lower()

    if not extension:
        raise HTTPException(
            status_code=422,
            detail="Uploaded file must have a file extension.",
        )

    mime_type = file.content_type or ""
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported MIME type '{mime_type}'. "
                f"Allowed types: {sorted(_ALLOWED_MIME_TYPES)}."
            ),
        )

    if extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file extension '{extension}'. "
                f"Allowed extensions: {sorted(_ALLOWED_EXTENSIONS)}."
            ),
        )

    content: bytes = await file.read()
    file_size: int = len(content)

    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File size {file_size:,} bytes exceeds the maximum of "
                f"{settings.MAX_UPLOAD_SIZE_MB} MB ({max_bytes:,} bytes)."
            ),
        )

    if file_size < _MIN_FILE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"File size {file_size} bytes is too small to be a valid audio file. "
                f"Minimum is {_MIN_FILE_BYTES} bytes."
            ),
        )

    return content, file_size, mime_type, extension


def save_file(
    content: bytes,
    session_id: uuid.UUID,
    response_id: uuid.UUID,
    extension: str,
    upload_dir: str,
) -> str:
    """Write content bytes to disk atomically and return the relative path.

    Creates the per-session subdirectory if it does not exist, writes the
    content to a temporary file, then atomically replaces the final path.

    Returns:
        Relative path string in the form '{session_id}/{response_id}{extension}'.
        Store this value in the DB. Resolve it at runtime by prepending
        settings.UPLOAD_DIR — never store the absolute path.

    Why upload_dir is a parameter (not read from settings here):
        Tests pass str(tmp_path) directly. The router reads settings.UPLOAD_DIR
        and passes it in. This separates I/O from configuration lookup,
        making save_file testable without patching settings or the environment.

    Why relative paths are returned and stored:
        If the Docker volume is remounted at a different host path, or
        UPLOAD_DIR is changed in settings, all existing DB rows remain valid.
        An absolute path stored in the DB would break every row on any
        infrastructure change.

    Why os.replace() instead of os.rename():
        On Windows, os.rename() raises FileExistsError if the destination
        already exists. On Linux/Docker (POSIX), os.replace() calls the
        rename(2) syscall — Python explicitly guarantees atomicity on all POSIX
        platforms. The destination is either the old file or the new file,
        never a partial write. On Windows, os.replace() uses MoveFileExW with
        MOVEFILE_REPLACE_EXISTING; Python makes no atomicity guarantee there,
        but unlike os.rename() it does not raise if the destination exists.
        For a re-upload of the same response_id, os.replace() safely replaces
        the prior file without raising on any platform.

    Atomic write pattern:
        1. Write all bytes to '{final_path}.tmp'.
        2. os.replace(tmp, final) — atomic rename on POSIX.
        3. On any exception, clean up the .tmp file before re-raising.
        The final file path never exists in a partially-written state.
    """
    rel_path = f"{session_id}/{response_id}{extension}"

    session_dir = Path(upload_dir) / str(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    final_path = session_dir / f"{response_id}{extension}"
    tmp_path = Path(str(final_path) + ".tmp")

    try:
        tmp_path.write_bytes(content)
        os.replace(tmp_path, final_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return rel_path


def create_response_record(
    db: Session,
    session: InterviewSession,
    question_id: uuid.UUID,
    user_id: uuid.UUID,
    file_path: str,
    file_size: int,
    mime_type: str,
    response_id: uuid.UUID | None = None,
) -> AudioResponse:
    """Insert an AudioResponse row and return the refreshed ORM object.

    response_id: when provided, the row is inserted with this UUID as its
    primary key. The router pre-generates this UUID so that the filename
    written by save_file() ({response_id}.ext) matches the DB row's id.
    Without this parameter, the ORM would generate a different UUID for the
    row, causing a permanent mismatch between the filename and the row id.

    Status defaults to RESPONSE_STATUS_UPLOADED ('uploaded'). The Week 3
    pipeline transitions it to 'processing' → 'completed' or 'failed'.

    Session state machine: this is the first AudioResponse ever recorded for
    a session exactly when session.status is still SESSION_STATUS_DRAFT —
    advance it to SESSION_STATUS_IN_PROGRESS here so draft-only operations
    (question regeneration, session metadata edits) are rejected from this
    point on. Any later upload finds session.status already
    'in_progress' (or beyond), so this branch does not fire again — the
    transition happens exactly once.

    commit() + refresh() ensures the caller receives the server-generated
    created_at and id values from the DB. The session status change is
    flushed in the same commit, so the AudioResponse insert and the session
    transition are atomic.
    """
    row_id = response_id if response_id is not None else uuid.uuid4()
    response = AudioResponse(
        id=row_id,
        session_id=session.id,
        question_id=question_id,
        user_id=user_id,
        file_path=file_path,
        file_size_bytes=file_size,
        mime_type=mime_type,
        status=RESPONSE_STATUS_UPLOADED,
    )
    db.add(response)

    if session.status == SESSION_STATUS_DRAFT:
        session.status = SESSION_STATUS_IN_PROGRESS

    db.commit()
    db.refresh(response)
    return response
