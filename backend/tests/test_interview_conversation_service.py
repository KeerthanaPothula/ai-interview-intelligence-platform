"""Unit tests for interview_conversation_service's Gemini response handling.

Regression coverage for the bug where response.text is None (Gemini
returned a response with no usable text — e.g. blocked by content/safety
filtering) and .strip() on it raised an unhandled AttributeError that
reached the global 500 handler instead of a clear service error.
"""

import pytest

from app.core.exceptions import AIServiceError
from app.services import interview_conversation_service as svc


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text

    def generate_content(self, model, contents):
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text):
        self.models = _FakeModels(text)


def _use_fake_client(monkeypatch, text):
    monkeypatch.setattr(svc, "_get_client", lambda: _FakeClient(text))


# ---------------------------------------------------------------------------
# generate_opening_question
# ---------------------------------------------------------------------------


def test_generate_opening_question_returns_stripped_text(monkeypatch):
    _use_fake_client(monkeypatch, "  What drew you to this role?  ")
    result = svc.generate_opening_question(
        job_role="Engineer", job_description="A backend role."
    )
    assert result == "What drew you to this role?"


def test_generate_opening_question_raises_ai_service_error_when_text_is_none(
    monkeypatch,
):
    _use_fake_client(monkeypatch, None)
    with pytest.raises(AIServiceError) as exc_info:
        svc.generate_opening_question(
            job_role="Engineer", job_description="A backend role."
        )
    assert exc_info.value.status_code == 502
    assert "Opening question generation" in exc_info.value.detail


def test_generate_opening_question_raises_ai_service_error_when_text_is_empty(
    monkeypatch,
):
    """Gemini can also return a present-but-empty text part; treated the
    same as None — neither is a usable question."""
    _use_fake_client(monkeypatch, "")
    with pytest.raises(AIServiceError):
        svc.generate_opening_question(
            job_role="Engineer", job_description="A backend role."
        )


# ---------------------------------------------------------------------------
# generate_follow_up_question
# ---------------------------------------------------------------------------


def test_generate_follow_up_question_returns_stripped_text(monkeypatch):
    _use_fake_client(monkeypatch, "  Tell me more about that.  ")
    text, difficulty = svc.generate_follow_up_question(
        job_role="Engineer",
        job_description="A backend role.",
        conversation_history=[
            {"turn_number": 1, "question_text": "Q1", "response_text": "A1"}
        ],
        current_turn=1,
        max_turns=3,
    )
    assert text == "Tell me more about that."
    assert difficulty == 3


def test_generate_follow_up_question_raises_ai_service_error_when_text_is_none(
    monkeypatch,
):
    _use_fake_client(monkeypatch, None)
    with pytest.raises(AIServiceError) as exc_info:
        svc.generate_follow_up_question(
            job_role="Engineer",
            job_description="A backend role.",
            conversation_history=[
                {"turn_number": 1, "question_text": "Q1", "response_text": "A1"}
            ],
            current_turn=1,
            max_turns=3,
        )
    assert exc_info.value.status_code == 502
    assert "Follow-up interview question generation" in exc_info.value.detail


# ---------------------------------------------------------------------------
# generate_interview_summary
# ---------------------------------------------------------------------------


def test_generate_interview_summary_returns_stripped_text(monkeypatch):
    _use_fake_client(monkeypatch, "  Strong communicator, solid technical depth.  ")
    result = svc.generate_interview_summary(
        job_role="Engineer",
        conversation_history=[
            {"turn_number": 1, "question_text": "Q1", "response_text": "A1"}
        ],
    )
    assert result == "Strong communicator, solid technical depth."


def test_generate_interview_summary_raises_ai_service_error_when_text_is_none(
    monkeypatch,
):
    """The confirmed root cause: a blocked/empty Gemini response (text=None)
    for the summary prompt, which embeds the full candidate-authored
    conversation and is therefore the most likely of the three prompts to
    trip content/safety filtering."""
    _use_fake_client(monkeypatch, None)
    with pytest.raises(AIServiceError) as exc_info:
        svc.generate_interview_summary(
            job_role="Engineer",
            conversation_history=[
                {"turn_number": 1, "question_text": "Q1", "response_text": "A1"}
            ],
        )
    assert exc_info.value.status_code == 502
    assert "Interview summary generation" in exc_info.value.detail
    assert "AI did not return a usable response" in exc_info.value.detail


def test_generate_interview_summary_raises_ai_service_error_when_text_is_empty(
    monkeypatch,
):
    _use_fake_client(monkeypatch, "")
    with pytest.raises(AIServiceError):
        svc.generate_interview_summary(
            job_role="Engineer",
            conversation_history=[
                {"turn_number": 1, "question_text": "Q1", "response_text": "A1"}
            ],
        )
