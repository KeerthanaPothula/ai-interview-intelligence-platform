"""Content-based file validation: magic bytes, filename sanitization, and
a malware-scan hook interface.

MIME type and extension (already checked by upload_service/documents.py)
are both client-supplied and trivially spoofable — a malicious actor can
send `Content-Type: audio/mpeg` with a filename ending in `.mp3` for any
payload. Checking the file's actual leading bytes ("magic bytes") against
the signature expected for the declared type catches that class of
spoofing without needing a full content-sniffing library.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Magic-byte signatures
# ---------------------------------------------------------------------------

# Audio/video container signatures, keyed by the declared MIME type.
# audio/mp4, audio/x-m4a, and video/mp4 share the ISO base media file
# format, which stores its signature ("ftyp") at byte offset 4, not 0 —
# handled as a special case in looks_like_declared_audio_type below.
_AUDIO_SIGNATURES: dict[str, bytes] = {
    "audio/wav": b"RIFF",
    "audio/webm": b"\x1a\x45\xdf\xa3",
    "video/webm": b"\x1a\x45\xdf\xa3",
    "audio/ogg": b"OggS",
}

_ISO_BMFF_MIME_TYPES = frozenset({"audio/mp4", "audio/x-m4a", "video/mp4"})

_DOCUMENT_SIGNATURES: dict[str, bytes] = {
    "application/pdf": b"%PDF",
    # .docx is a ZIP archive — every ZIP-based format starts with this
    # local-file-header signature.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        b"PK\x03\x04"
    ),
}


def looks_like_declared_audio_type(content: bytes, mime_type: str) -> bool:
    """Return True if `content`'s leading bytes match the signature
    expected for `mime_type`. Returns True for any MIME type with no
    known signature (caller still has the extension/MIME allow-list as
    the primary filter)."""
    if mime_type in _ISO_BMFF_MIME_TYPES:
        return len(content) >= 8 and content[4:8] == b"ftyp"

    if mime_type == "audio/mpeg":
        if content[:3] == b"ID3":
            return True
        # Raw MPEG frame sync: 11 set bits (0xFFE0 mask) at the start of
        # the first frame — there is no universal container header for
        # ID3-less MP3 files.
        return len(content) >= 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0

    signature = _AUDIO_SIGNATURES.get(mime_type)
    if signature is None:
        return True
    return content.startswith(signature)


def looks_like_declared_document_type(content: bytes, mime_type: str) -> bool:
    """Same idea as looks_like_declared_audio_type, for resume uploads."""
    signature = _DOCUMENT_SIGNATURES.get(mime_type)
    if signature is None:
        return True
    return content.startswith(signature)


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe version of a client-supplied filename.

    Strips directory components (defeats path traversal via '../' or an
    absolute path in the filename field), normalizes unicode, and
    replaces any character outside [A-Za-z0-9._-] with '_'.

    save_file() (upload_service.py) always writes under a server-generated
    UUID filename, never the client-supplied name, so this function is a
    defense-in-depth measure for the original filename wherever it is
    persisted for display (e.g. ResumeDocument.filename) rather than used
    as a path component.
    """
    name = unicodedata.normalize("NFKC", filename)
    name = Path(name).name
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    return name or "unnamed"


# ---------------------------------------------------------------------------
# Malware scanning — stub integration point
# ---------------------------------------------------------------------------


def scan_for_malware(content: bytes) -> bool:
    """Return True if `content` is considered clean.

    Stub integration point for a real scanner — e.g. ClamAV via a clamd
    socket, or a cloud scanning API. Always returns True today. Wire a
    real scanner call here before accepting user-uploaded files in any
    deployment that needs malware protection; the call site (upload_service
    and documents.py) already treats a False return as a rejected upload.
    """
    return True
