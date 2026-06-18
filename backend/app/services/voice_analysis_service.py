"""Voice Analytics Engine — librosa-based speaking metrics.

This service analyses an audio file and transcript to produce a set of
speaking-quality metrics and a composite confidence score (0–100).

Librosa is imported lazily inside analyze_audio() so that modules that
merely import this service (e.g. tests that mock the function) do not
require librosa to be installed.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Filler words to detect in the transcript.
_FILLER_PATTERNS = [
    r"\bum\b",
    r"\buh\b",
    r"\blike\b",
    r"\byou know\b",
    r"\bactually\b",
    r"\bbasically\b",
]


def _count_filler_words(transcript_text: str) -> int:
    """Count filler-word occurrences in transcript_text using whole-word regex."""
    text_lower = transcript_text.lower()
    total = 0
    for pattern in _FILLER_PATTERNS:
        total += len(re.findall(pattern, text_lower))
    return total


def _compute_confidence_score(
    speaking_rate: float,
    filler_word_count: int,
    word_count: int,
    pause_count: int,
    long_pause_count: int,
    energy_consistency: float,
    duration_seconds: int | None,
) -> int:
    """Return a composite confidence score in [0, 100].

    Weights:
      25% speaking rate quality (optimal 120–160 WPM)
      25% filler word density (per 100 words)
      20% pause frequency (pauses per minute)
      15% long-pause penalty
      15% energy (volume) consistency
    """
    # Speaking rate score
    if 120 <= speaking_rate <= 160:
        rate_score = 100.0
    elif speaking_rate > 0:
        rate_score = max(0.0, 100.0 - abs(speaking_rate - 140) * 0.5)
    else:
        rate_score = 50.0

    # Filler word density score
    filler_density = (filler_word_count / max(word_count, 1)) * 100
    filler_score = max(0.0, 100.0 - filler_density * 10)

    # Pause frequency score
    duration_minutes = (duration_seconds or 0) / 60
    if duration_minutes > 0:
        pause_frequency = pause_count / duration_minutes
        pause_score = max(0.0, 100.0 - max(0.0, pause_frequency - 5) * 5)
    else:
        pause_score = 50.0

    # Long-pause penalty score
    long_pause_score = max(0.0, 100.0 - long_pause_count * 15)

    # Energy consistency score (already in [0, 1])
    energy_score = energy_consistency * 100

    composite = (
        rate_score * 0.25
        + filler_score * 0.25
        + pause_score * 0.20
        + long_pause_score * 0.15
        + energy_score * 0.15
    )
    return max(0, min(100, int(composite)))


def analyze_audio(
    file_path: str,
    transcript_text: str,
    word_count: int,
    duration_seconds: int | None,
) -> dict:
    """Analyse audio and return voice metrics.

    Args:
        file_path: Absolute path to the audio file.
        transcript_text: The Whisper transcript (used for filler-word detection).
        word_count: Number of words in the transcript (from Whisper).
        duration_seconds: Audio duration in whole seconds (from Whisper).

    Returns:
        dict with keys:
            speaking_rate, average_pause_duration, total_pause_time,
            long_pause_count, filler_word_count, energy_consistency,
            confidence_score
    """
    import numpy as np

    try:
        import librosa
    except ImportError:
        logger.error("librosa is not installed; voice analytics unavailable")
        raise

    # ------------------------------------------------------------------
    # Load audio (mono, 16 kHz — consistent with Whisper's resampling)
    # ------------------------------------------------------------------
    y, sr = librosa.load(file_path, sr=16000, mono=True)

    # ------------------------------------------------------------------
    # Speaking rate (words per minute)
    # ------------------------------------------------------------------
    if duration_seconds and duration_seconds > 0 and word_count > 0:
        speaking_rate = round((word_count / duration_seconds) * 60, 1)
    else:
        speaking_rate = 0.0

    # ------------------------------------------------------------------
    # Pause detection via RMS energy thresholding
    # ------------------------------------------------------------------
    frame_length = 2048
    hop_length = 512
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    times = librosa.frames_to_time(
        np.arange(len(rms)), sr=sr, hop_length=hop_length
    )

    # Silence = below 10 % of mean RMS energy
    silence_threshold = float(np.mean(rms)) * 0.10
    is_silent = rms < silence_threshold

    pauses: list[float] = []
    in_pause = False
    pause_start = 0.0

    for i, silent in enumerate(is_silent):
        if silent and not in_pause:
            in_pause = True
            pause_start = float(times[i])
        elif not silent and in_pause:
            in_pause = False
            duration = float(times[i]) - pause_start
            if duration > 0.3:  # ignore micro-pauses shorter than 300 ms
                pauses.append(duration)

    if in_pause and len(times) > 0:
        duration = float(times[-1]) - pause_start
        if duration > 0.3:
            pauses.append(duration)

    pause_count = len(pauses)
    average_pause_duration = round(float(np.mean(pauses)), 2) if pauses else 0.0
    total_pause_time = round(sum(pauses), 2)
    long_pause_count = sum(1 for p in pauses if p > 2.0)

    # ------------------------------------------------------------------
    # Filler word detection from transcript
    # ------------------------------------------------------------------
    filler_word_count = _count_filler_words(transcript_text)

    # ------------------------------------------------------------------
    # Energy (volume) consistency
    # energy_consistency ∈ [0, 1]: 1 = very consistent, 0 = highly variable
    # ------------------------------------------------------------------
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))
    if energy_mean > 0:
        cv = energy_std / energy_mean  # coefficient of variation
        energy_consistency = round(max(0.0, min(1.0, 1.0 - min(cv, 1.0))), 2)
    else:
        energy_consistency = 0.0

    # ------------------------------------------------------------------
    # Composite confidence score
    # ------------------------------------------------------------------
    confidence_score = _compute_confidence_score(
        speaking_rate=speaking_rate,
        filler_word_count=filler_word_count,
        word_count=word_count,
        pause_count=pause_count,
        long_pause_count=long_pause_count,
        energy_consistency=energy_consistency,
        duration_seconds=duration_seconds,
    )

    logger.info(
        "Voice analysis complete: speaking_rate=%.1f WPM, pauses=%d, "
        "fillers=%d, energy_consistency=%.2f, confidence=%d",
        speaking_rate,
        pause_count,
        filler_word_count,
        energy_consistency,
        confidence_score,
    )

    return {
        "speaking_rate": speaking_rate,
        "average_pause_duration": average_pause_duration,
        "total_pause_time": total_pause_time,
        "long_pause_count": long_pause_count,
        "filler_word_count": filler_word_count,
        "energy_consistency": energy_consistency,
        "confidence_score": confidence_score,
    }
