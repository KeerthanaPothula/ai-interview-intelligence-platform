"""Tests for rag_service.generate_rag_questions — Gemini output validation.

RAG questions go through the same per-item validation as standard question
generation (gemini_service.normalize_questions), against a fake client.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core import ai_reliability
from app.core.exceptions import AIServiceError
from app.services import rag_service


class _FastSettings:
    GEMINI_MAX_RETRIES = 2
    GEMINI_RETRY_BACKOFF_SECONDS = 0.001
    GEMINI_MODEL = "gemini-test-model"


@pytest.fixture(autouse=True)
def _fast_settings(monkeypatch):
    monkeypatch.setattr(ai_reliability, "get_settings", lambda: _FastSettings())
    monkeypatch.setattr(rag_service, "get_settings", lambda: _FastSettings())


def _gemini_returns(monkeypatch, fn):
    class _Models:
        def generate_content(self, *, model, contents):
            return fn()

    class _Client:
        models = _Models()

    monkeypatch.setattr(rag_service, "_get_client", lambda: _Client())


def _text(payload):
    class _Response:
        text = payload if isinstance(payload, str) else json.dumps(payload)

    return lambda: _Response()


def _generate(count=3):
    return rag_service.generate_rag_questions(
        job_role="Backend Engineer",
        job_description="Python APIs.",
        relevant_chunks=["Built FastAPI services."],
        count=count,
    )


def test_valid_output_is_returned_normalized(monkeypatch):
    _gemini_returns(
        monkeypatch,
        _text(
            "```json\n"
            + json.dumps(
                [
                    {"body": " Tell me about FastAPI. ", "category": "technical"},
                    {"body": "A hard deadline?", "category": "situational"},
                ]
            )
            + "\n```"
        ),
    )

    assert _generate(count=2) == [
        {
            "body": "Tell me about FastAPI.",
            "category": "technical",
            "sequence_order": 1,
        },
        {"body": "A hard deadline?", "category": "situational", "sequence_order": 2},
    ]


def test_invalid_items_and_fields_are_normalized(monkeypatch):
    _gemini_returns(
        monkeypatch,
        _text(
            [
                {"body": "", "category": "technical"},  # empty body: dropped
                "not an object",  # dropped
                {"body": "Q1", "category": "trivia", "sequence_order": 9},
                {"body": "Q2"},  # missing category
                {"body": "Q3", "category": "behavioral"},
                {"body": "Q4", "category": "technical"},  # beyond count
            ]
        ),
    )

    assert _generate(count=3) == [
        {"body": "Q1", "category": "behavioral", "sequence_order": 1},
        {"body": "Q2", "category": "behavioral", "sequence_order": 2},
        {"body": "Q3", "category": "behavioral", "sequence_order": 3},
    ]


def test_fewer_valid_questions_than_requested_are_still_returned(monkeypatch):
    _gemini_returns(monkeypatch, _text([{"body": "Only one", "category": "technical"}]))

    assert [q["body"] for q in _generate(count=5)] == ["Only one"]


@pytest.mark.parametrize(
    "payload",
    ["this is not json", '{"body": "an object, not a list"}', "[]", '[{"body": ""}]'],
)
def test_malformed_or_empty_output_raises(monkeypatch, payload):
    _gemini_returns(monkeypatch, _text(payload))

    with pytest.raises(AIServiceError):
        _generate()


def test_gemini_failure_raises_ai_service_error(monkeypatch):
    def _down():
        raise httpx.ConnectError("unreachable")

    _gemini_returns(monkeypatch, _down)

    with pytest.raises(AIServiceError) as exc_info:
        _generate()
    assert exc_info.value.status_code == 502
