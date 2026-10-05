"""Tests for rag_service: Gemini question validation and resume embeddings.

RAG questions go through the same per-item validation as standard question
generation (gemini_service.normalize_questions), against a fake client.
Embedding tests inject a fake model — the real HuggingFace model is never
downloaded or loaded.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import uuid

import httpx
import pytest

from app.config import get_settings
from app.core import ai_reliability
from app.core.exceptions import AIServiceError
from app.models.documents import DocumentChunk
from app.services import embedding_service, rag_service


class _FastSettings:
    GEMINI_MAX_RETRIES = 2
    GEMINI_RETRY_BACKOFF_SECONDS = 0.001
    GEMINI_MODEL = "gemini-test-model"
    ENABLE_EMBEDDINGS = True
    RAG_CHUNK_SIZE = 200
    RAG_CHUNK_OVERLAP = 50


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


# ---------------------------------------------------------------------------
# Embeddings: ENABLE_EMBEDDINGS on/off
# ---------------------------------------------------------------------------


class _Vec(list):
    def tolist(self):
        return list(self)


class _FakeModel:
    """Two-dimensional "semantic" space: [python-ness, sales-ness]."""

    def __init__(self, fail: Exception | None = None):
        self.fail = fail

    def encode(self, text, normalize_embeddings):
        if self.fail is not None:
            raise self.fail
        t = text.lower()
        v = [float("python" in t), float("sales" in t)]
        n = math.hypot(*v) or 1.0
        return _Vec(x / n for x in v)


def _set_embeddings(monkeypatch, enabled: bool):
    # rag_service reads the stub above; embedding_service the real settings.
    monkeypatch.setattr(_FastSettings, "ENABLE_EMBEDDINGS", enabled)
    monkeypatch.setattr(get_settings(), "ENABLE_EMBEDDINGS", enabled)


def _block_model_import(monkeypatch):
    """Unload any model and make importing sentence-transformers fail."""
    monkeypatch.setattr(embedding_service, "_model", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)


def _record_encode_attempts(monkeypatch):
    """Record every encode_text call. A swallowed failure would hide an
    attempt, so disabled-mode tests assert this list stays empty."""
    calls = []

    def _recording(text):
        calls.append(text)
        raise AssertionError("encode_text must not run when embeddings are off")

    monkeypatch.setattr(embedding_service, "encode_text", _recording)
    return calls


def _store(db, user_id, chunks):
    stored = rag_service.store_chunks(
        user_id=uuid.UUID(user_id),
        chunks=chunks,
        source_type="resume",
        resume_document_id=None,
        db=db,
    )
    db.commit()
    return stored


def _rows(db, user_id):
    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.user_id == uuid.UUID(user_id))
        .order_by(DocumentChunk.chunk_index)
        .all()
    )


def _retrieve(db, user_id, query, k):
    return rag_service.retrieve_relevant_chunks(
        query_text=query, user_id=uuid.UUID(user_id), db=db, k=k
    )


_CHUNKS = ["Sales and marketing lead", "Python FastAPI backend engineer"]


def test_enabled_stores_embeddings_and_retrieves_semantically(
    db, registered_user, monkeypatch
):
    _set_embeddings(monkeypatch, True)
    monkeypatch.setattr(embedding_service, "_model", _FakeModel())

    assert _store(db, registered_user["id"], _CHUNKS) == 2
    rows = _rows(db, registered_user["id"])
    assert [json.loads(r.embedding_json) for r in rows] == [[0.0, 1.0], [1.0, 0.0]]

    # Semantic ranking, not storage order (the sales chunk is stored first).
    top = _retrieve(db, registered_user["id"], "python developer", k=1)
    assert top == ["Python FastAPI backend engineer"]


def test_disabled_never_loads_model_and_stores_chunks_without_embeddings(
    db, registered_user, monkeypatch
):
    _set_embeddings(monkeypatch, False)
    _block_model_import(monkeypatch)
    attempts = _record_encode_attempts(monkeypatch)

    assert _store(db, registered_user["id"], _CHUNKS) == 2
    rows = _rows(db, registered_user["id"])
    assert [r.chunk_text for r in rows] == _CHUNKS
    assert all(r.embedding_json is None for r in rows)
    assert attempts == []
    assert embedding_service._model is None


def test_disabled_retrieval_uses_first_k_and_keeps_existing_embeddings(
    db, registered_user, monkeypatch
):
    # Rows embedded while enabled (e.g. before the switch) stay untouched.
    _set_embeddings(monkeypatch, True)
    monkeypatch.setattr(embedding_service, "_model", _FakeModel())
    _store(db, registered_user["id"], _CHUNKS)
    before = [r.embedding_json for r in _rows(db, registered_user["id"])]

    _set_embeddings(monkeypatch, False)
    _block_model_import(monkeypatch)
    attempts = _record_encode_attempts(monkeypatch)

    top = _retrieve(db, registered_user["id"], "python developer", k=1)
    assert top == [_CHUNKS[0]]  # first-k fallback, no semantic ranking
    assert attempts == []
    assert [r.embedding_json for r in _rows(db, registered_user["id"])] == before
    assert embedding_service._model is None


def test_disabled_model_loader_refuses_before_importing(monkeypatch):
    _set_embeddings(monkeypatch, False)
    _block_model_import(monkeypatch)

    # RuntimeError from the guard, not ImportError from attempting the import.
    with pytest.raises(RuntimeError, match="ENABLE_EMBEDDINGS=false"):
        embedding_service.encode_text("anything")


def test_enabled_embedding_failure_stores_chunk_and_logs_reason(
    db, registered_user, monkeypatch, caplog
):
    _set_embeddings(monkeypatch, True)
    monkeypatch.setattr(
        embedding_service,
        "_model",
        _FakeModel(fail=OSError("PermissionError at /home/appuser/.cache")),
    )

    with caplog.at_level(logging.WARNING, logger="app.services.rag_service"):
        assert _store(db, registered_user["id"], _CHUNKS[:1]) == 1

    assert _rows(db, registered_user["id"])[0].embedding_json is None
    assert "Embedding failed for chunk 0" in caplog.text
    assert "PermissionError at /home/appuser/.cache" in caplog.text


@pytest.mark.parametrize("enabled", [True, False])
def test_resume_upload_succeeds_without_exposing_embedding_errors(
    client, auth_headers, db, registered_user, upload_dir, monkeypatch, enabled
):
    from tests.test_documents import _make_pdf, _mock_extract

    _set_embeddings(monkeypatch, enabled)
    _block_model_import(monkeypatch)
    if enabled:
        # The model fails, as it does with an unwritable HuggingFace cache.
        monkeypatch.setattr(
            embedding_service, "_model", _FakeModel(fail=OSError("internal-path"))
        )
    else:
        attempts = _record_encode_attempts(monkeypatch)
    monkeypatch.setattr(
        "app.routers.documents.document_extraction_service.extract_text",
        _mock_extract,
    )

    resp = client.post(
        "/api/v1/documents/resume/upload",
        files={"file": ("cv.pdf", _make_pdf(), "application/pdf")},
        headers=auth_headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["chunk_count"] >= 1
    assert "internal-path" not in resp.text
    rows = _rows(db, registered_user["id"])
    assert rows and all(r.embedding_json is None for r in rows)
    if not enabled:
        assert attempts == []
