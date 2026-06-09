from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResponseStatus = Literal["uploaded", "processing", "completed", "failed"]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AudioResponseCreate(BaseModel):
    """Form metadata for POST /interviews/{session_id}/responses.

    The audio file itself is received as a multipart UploadFile and is not
    part of this schema. This schema validates only the structured metadata
    that accompanies the upload.
    """

    question_id: uuid.UUID = Field(
        description=(
            "UUID of the Question this recording answers. "
            "Must belong to the same session as the upload endpoint's session_id."
        )
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
#
# Three storage fields are intentionally absent from all response schemas:
#
#   file_path   — leaks the server's upload directory structure and file-naming
#                 convention. A client that knows the path could probe file
#                 existence or, if a future route serves static files, attempt
#                 path traversal. The client references recordings by UUID, not
#                 by filesystem path.
#
#   file_size_bytes, mime_type — internal bookkeeping used by the Week 3 pipeline.
#                 Surfacing them in the API would lock the storage format into
#                 the public contract, making it harder to change later.
#
#   user_id, session_id — derivable from the JWT and the URL respectively;
#                 echoing them adds payload size with no client benefit.
#
# error_message is exposed only via AudioResponseStatusResponse (the status
# polling endpoint) because:
#   - It is always null at upload time (status is always 'uploaded' immediately
#     after a successful upload — the pipeline has not run yet).
#   - The status endpoint is the correct place to surface pipeline failures
#     because that is when status == 'failed' can first occur.
#   - Keeping error_message off AudioResponseResponse prevents callers from
#     writing error-handling logic against a field that is always null there.


class AudioResponseResponse(BaseModel):
    """Returned immediately after a successful audio upload (POST .../responses).

    Contains the fields the client needs to track the recording:
    - id: reference the response in future status polls and UI
    - question_id: confirm which question was answered
    - status: always 'uploaded' at creation; changes as the pipeline processes
    - created_at: timestamp for display and ordering

    Does not include error_message — see module docstring above.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for this audio response.")
    question_id: uuid.UUID = Field(
        description="UUID of the question this recording answers."
    )
    status: ResponseStatus = Field(
        description=(
            "Processing state: 'uploaded' → 'processing' → 'completed' or 'failed'. "
            "Always 'uploaded' immediately after creation."
        )
    )
    created_at: datetime = Field(description="UTC timestamp of upload.")


class AudioResponseStatusResponse(BaseModel):
    """Returned by the status polling endpoint (GET .../responses/{id}/status).

    Includes error_message so clients can surface pipeline failure details.
    This is the only context where status can be 'failed' and error_message
    can be non-null — the pipeline (Week 3) sets both fields together.

    Polling pattern:
        Client polls until status is 'completed' or 'failed'.
        On 'failed', error_message contains a human-readable reason.
        On 'completed', downstream results are available via the analysis
        endpoints added in Week 3.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Unique identifier for this audio response.")
    status: ResponseStatus = Field(
        description=(
            "Current processing state: 'uploaded', 'processing', "
            "'completed', or 'failed'."
        )
    )
    created_at: datetime = Field(description="UTC timestamp of upload.")
    error_message: str | None = Field(
        None,
        description=(
            "Human-readable failure reason set by the processing pipeline. "
            "Non-null only when status == 'failed'; null for all other states."
        ),
    )
