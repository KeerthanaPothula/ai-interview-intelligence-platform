"""Tests for app.core.exceptions — the typed exception hierarchy and the
global FastAPI handlers registered by register_exception_handlers().

Endpoint-level 404/422 behavior driven by these exceptions is already
exercised indirectly by the router test suites (test_interviews.py,
test_follow_up.py, test_reports.py, etc). These tests target the handler
wiring itself, including the catch-all 500 path, which no router test
exercises directly because no route is expected to raise a bare exception.
A standalone FastAPI app (not the production `app`) is used so test routes
that deliberately raise exceptions are never reachable in production.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from app.core.exceptions import (
    AIServiceError,
    AppException,
    FileValidationError,
    ResourceNotFound,
    UnauthorizedAccess,
    ValidationError,
    register_exception_handlers,
)


class _Body(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name must not be blank")
        return v


@pytest.fixture
def test_app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/resource-not-found")
    def _raise_not_found():
        raise ResourceNotFound("Widget not found.")

    @app.get("/unauthorized")
    def _raise_unauthorized():
        raise UnauthorizedAccess()

    @app.get("/validation-error")
    def _raise_validation():
        raise ValidationError("Bad input.")

    @app.get("/ai-service-error")
    def _raise_ai_error():
        raise AIServiceError()

    @app.get("/file-validation-error")
    def _raise_file_error():
        raise FileValidationError()

    @app.get("/boom")
    def _raise_unexpected():
        raise RuntimeError("something broke internally")

    @app.post("/validated-body")
    def _validated_body(body: _Body):
        return {"name": body.name}

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Exception class defaults
# ---------------------------------------------------------------------------


def test_resource_not_found_default_status_and_detail():
    exc = ResourceNotFound()
    assert exc.status_code == 404
    assert exc.detail == "Resource not found."


def test_unauthorized_access_default_status():
    assert UnauthorizedAccess().status_code == 401


def test_validation_error_default_status():
    assert ValidationError().status_code == 422


def test_ai_service_error_default_status():
    assert AIServiceError().status_code == 502


def test_ai_service_error_overridable_status():
    exc = AIServiceError("rate limited", status_code=503)
    assert exc.status_code == 503


def test_file_validation_error_default_status():
    assert FileValidationError().status_code == 422


def test_app_exception_base_defaults_to_500():
    assert AppException("oops").status_code == 500


# ---------------------------------------------------------------------------
# Global handlers wired into a FastAPI app
# ---------------------------------------------------------------------------


def test_handler_returns_404_for_resource_not_found(client):
    response = client.get("/resource-not-found")
    assert response.status_code == 404
    assert response.json() == {"detail": "Widget not found."}


def test_handler_returns_401_for_unauthorized(client):
    response = client.get("/unauthorized")
    assert response.status_code == 401


def test_handler_returns_422_for_validation_error(client):
    response = client.get("/validation-error")
    assert response.status_code == 422
    assert response.json() == {"detail": "Bad input."}


def test_handler_returns_502_for_ai_service_error(client):
    response = client.get("/ai-service-error")
    assert response.status_code == 502


def test_handler_returns_422_for_file_validation_error(client):
    response = client.get("/file-validation-error")
    assert response.status_code == 422


def test_handler_returns_generic_500_for_unexpected_exception(client):
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    # The raw exception message must never leak to the client.
    assert "something broke internally" not in response.text


def test_handler_serializes_validation_error_with_value_error_in_ctx(client):
    """Regression test: RequestValidationError.errors() embeds a raw
    ValueError instance in the 'ctx' field for field_validator failures.
    JSONResponse's default encoder cannot serialize a ValueError directly —
    the handler must run errors() through jsonable_encoder() first.
    """
    response = client.post("/validated-body", json={"name": "   "})
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
