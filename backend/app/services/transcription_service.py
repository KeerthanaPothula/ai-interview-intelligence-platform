from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.core.metrics import observe_ai_request
from app.core.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# ---------------------------------------------------------------------------
# Whisper singleton
#
# _model is None until the first call to get_model(). After initialization it
# is a read-only reference — the only write is inside the lock in get_model().
#
# _model_lock serializes initialization only. It is never held during
# transcription; inference concurrency is controlled by the semaphore in
# processing_service (see Thread Safety Review below).
#
# whisper (and therefore PyTorch) is NOT imported at module level.
# The `import whisper` statement is deferred to the first call to get_model(),
# inside the lock — so PyTorch is only loaded into memory when a real
# transcription is requested. With ENABLE_AUDIO_PROCESSING=false the import
# never happens, keeping idle RAM well under Render Free's 512 MB limit.
# ---------------------------------------------------------------------------

_model: Any | None = None
_model_lock = threading.Lock()


def get_model() -> Any:
    """Return the loaded Whisper model, loading it exactly once per process.

    Raises RuntimeError immediately if ENABLE_AUDIO_PROCESSING is false so
    the caller gets a clear diagnostic rather than an ImportError or a
    cryptic failure from whisper.load_model.

    Double-checked locking:
      - Outer check (no lock): fast path for all calls after first load.
        Reading a Python object reference is atomic under the GIL, so a
        non-None _model seen outside the lock is always a fully initialized
        object.
      - Inner check (inside lock): guards against two threads that both
        observed None simultaneously before either acquired the lock.
        The second thread to acquire the lock sees _model already set and
        skips the load.
    """
    global _model
    if not get_settings().ENABLE_AUDIO_PROCESSING:
        raise RuntimeError(
            "Audio processing is disabled (ENABLE_AUDIO_PROCESSING=false). "
            "Set ENABLE_AUDIO_PROCESSING=true and restart the server to enable "
            "Whisper transcription."
        )
    if _model is None:
        with _model_lock:
            if _model is None:
                import whisper  # lazy — PyTorch is not loaded until this point
                model_name = get_settings().WHISPER_MODEL
                logger.info("Loading Whisper model '%s'", model_name)
                _model = whisper.load_model(model_name)
                logger.info("Whisper model '%s' loaded", model_name)
    return _model


def transcribe_audio(file_path: str) -> dict[str, Any]:
    """Transcribe an audio file with Whisper and return structured results.

    Args:
        file_path: Absolute path to the audio file on disk.

    Returns:
        {
            "text": str,
            "language": str | None,
            "duration_seconds": int | None,
            "word_count": int,
        }

    Raises:
        FileNotFoundError: file_path does not exist on disk.
        RuntimeError:      ffmpeg is not installed or not on PATH.
        RuntimeError:      Transcription produced no text.
    """
    # ------------------------------------------------------------------
    # Pre-flight existence check.
    #
    # Whisper also raises FileNotFoundError when ffmpeg is missing (the
    # subprocess.Popen call for the ffmpeg executable fails). Confirming
    # the audio file exists here lets us unambiguously reclassify any
    # subsequent FileNotFoundError from model.transcribe() as an ffmpeg
    # problem — without inspecting exception messages.
    # ------------------------------------------------------------------
    if not Path(file_path).exists():
        logger.error("Audio file not found: %s", file_path)
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    model = get_model()
    stem = Path(file_path).name
    logger.info("Transcription started: %s", stem)

    start = time.perf_counter()
    with tracer.start_as_current_span("whisper.transcribe") as span:
        span.set_attribute("whisper.model", get_settings().WHISPER_MODEL)
        try:
            result: dict[str, Any] = model.transcribe(file_path, verbose=False)
        except FileNotFoundError:
            # The audio file exists (confirmed above). A FileNotFoundError from
            # model.transcribe() originates from Whisper's internal ffmpeg
            # subprocess call — the ffmpeg executable was not found on PATH.
            logger.error("Transcription failed: ffmpeg not found (file=%s)", stem)
            observe_ai_request(
                provider="whisper",
                operation="transcribe",
                status="error",
                duration_seconds=time.perf_counter() - start,
            )
            raise RuntimeError("ffmpeg is not installed or not available in PATH")
        except Exception as exc:
            logger.error("Transcription failed: %s (file=%s)", type(exc).__name__, stem)
            observe_ai_request(
                provider="whisper",
                operation="transcribe",
                status="error",
                duration_seconds=time.perf_counter() - start,
            )
            raise

    observe_ai_request(
        provider="whisper",
        operation="transcribe",
        status="success",
        duration_seconds=time.perf_counter() - start,
    )

    # ------------------------------------------------------------------
    # Result extraction
    # ------------------------------------------------------------------

    text: str = (result.get("text") or "").strip()

    if not text:
        logger.warning("Transcription produced no text: %s", stem)
        raise RuntimeError("Transcription produced no text")

    segments: list[dict[str, Any]] = result.get("segments", [])

    # ACR-001 rejected: duration stored as Integer. Whisper segment["end"]
    # is a float (e.g. 142.34); int() truncates to whole seconds.
    duration_seconds: int | None = int(segments[-1]["end"]) if segments else None

    word_count: int = len(text.split())

    # result["language"] is a BCP-47 code ("en", "fr", …) or absent.
    language: str | None = result.get("language") or None

    logger.info(
        "Transcription complete: %s — %d words, language=%s, duration=%ss",
        stem,
        word_count,
        language,
        duration_seconds,
    )

    return {
        "text": text,
        "language": language,
        "duration_seconds": duration_seconds,
        "word_count": word_count,
    }
