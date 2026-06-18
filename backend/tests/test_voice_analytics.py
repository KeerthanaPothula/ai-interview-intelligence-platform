"""Tests for the voice analytics service (librosa mocked).

librosa is imported *lazily* (inside analyze_audio()) so that the module can
be imported in test environments where librosa is not installed.  This means
`librosa` is NOT a module-level attribute of voice_analysis_service, so the
normal `@patch("app.services.voice_analysis_service.librosa")` approach does
not work.

Instead we inject a mock via `patch.dict(sys.modules, {"librosa": fake})` so
that `import librosa` inside analyze_audio() resolves to our mock object.
"""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.voice_analysis_service import (
    _compute_confidence_score,
    _count_filler_words,
    analyze_audio,
)


# ---------------------------------------------------------------------------
# _count_filler_words
# ---------------------------------------------------------------------------


def test_count_filler_words_basic():
    text = "Um, I think that, uh, you know, this is like basically what I do."
    count = _count_filler_words(text)
    # um=1, uh=1, you know=1, like=1, basically=1 → 5
    assert count == 5


def test_count_filler_words_case_insensitive():
    assert _count_filler_words("UM UH LIKE") == 3


def test_count_filler_words_whole_word_only():
    # "unlike" contains "like" but should not match the whole-word pattern.
    assert _count_filler_words("unlike similar") == 0


def test_count_filler_words_empty():
    assert _count_filler_words("") == 0


def test_count_filler_words_multiple_occurrences():
    text = "um, um, um"
    assert _count_filler_words(text) == 3


# ---------------------------------------------------------------------------
# _compute_confidence_score
# ---------------------------------------------------------------------------


def test_confidence_score_optimal_rate():
    score = _compute_confidence_score(
        speaking_rate=140.0,
        filler_word_count=0,
        word_count=140,
        pause_count=2,
        long_pause_count=0,
        energy_consistency=0.9,
        duration_seconds=60,
    )
    assert score >= 80


def test_confidence_score_too_fast():
    score = _compute_confidence_score(
        speaking_rate=250.0,
        filler_word_count=5,
        word_count=200,
        pause_count=0,
        long_pause_count=0,
        energy_consistency=0.5,
        duration_seconds=60,
    )
    assert 0 <= score <= 100


def test_confidence_score_many_fillers():
    score = _compute_confidence_score(
        speaking_rate=130.0,
        filler_word_count=20,
        word_count=100,
        pause_count=3,
        long_pause_count=2,
        energy_consistency=0.4,
        duration_seconds=60,
    )
    assert 0 <= score <= 100


def test_confidence_score_clamp_to_range():
    for rate in [0.0, 50.0, 140.0, 250.0]:
        score = _compute_confidence_score(
            speaking_rate=rate,
            filler_word_count=0,
            word_count=100,
            pause_count=0,
            long_pause_count=0,
            energy_consistency=1.0,
            duration_seconds=60,
        )
        assert 0 <= score <= 100, f"Score {score} out of range for rate={rate}"


# ---------------------------------------------------------------------------
# analyze_audio (librosa mocked)
# ---------------------------------------------------------------------------


def _make_mock_librosa() -> MagicMock:
    """Return a MagicMock that mimics the librosa API surface used by analyze_audio."""
    mock_lib = MagicMock()
    y = np.zeros(16000, dtype=np.float32)
    mock_lib.load.return_value = (y, 16000)
    rms = np.full((1, 32), 0.05, dtype=np.float32)
    mock_lib.feature.rms.return_value = rms
    mock_lib.frames_to_time.return_value = np.linspace(0, 1.0, 32)
    return mock_lib


def test_analyze_audio_returns_all_keys():
    """analyze_audio returns a dict with all expected keys."""
    mock_lib = _make_mock_librosa()
    with patch.dict(sys.modules, {"librosa": mock_lib}):
        result = analyze_audio(
            file_path="/fake/path.webm",
            transcript_text="I have experience building APIs with Python.",
            word_count=8,
            duration_seconds=3,
        )

    expected_keys = {
        "speaking_rate",
        "average_pause_duration",
        "total_pause_time",
        "long_pause_count",
        "filler_word_count",
        "energy_consistency",
        "confidence_score",
    }
    assert expected_keys == set(result.keys())


def test_analyze_audio_speaking_rate():
    mock_lib = _make_mock_librosa()
    with patch.dict(sys.modules, {"librosa": mock_lib}):
        result = analyze_audio(
            file_path="/fake/path.webm",
            transcript_text="word " * 100,
            word_count=100,
            duration_seconds=60,  # 100 words / 60 s → 100 WPM
        )
    assert result["speaking_rate"] == pytest.approx(100.0, abs=0.2)


def test_analyze_audio_filler_count():
    mock_lib = _make_mock_librosa()
    with patch.dict(sys.modules, {"librosa": mock_lib}):
        result = analyze_audio(
            file_path="/fake/path.webm",
            transcript_text="Um, I think uh you know this is like a test.",
            word_count=10,
            duration_seconds=5,
        )
    # um=1, uh=1, you know=1, like=1 → 4
    assert result["filler_word_count"] == 4


def test_analyze_audio_confidence_in_range():
    mock_lib = _make_mock_librosa()
    with patch.dict(sys.modules, {"librosa": mock_lib}):
        result = analyze_audio(
            file_path="/fake/path.webm",
            transcript_text="Clear structured answer.",
            word_count=3,
            duration_seconds=2,
        )
    assert 0 <= result["confidence_score"] <= 100
