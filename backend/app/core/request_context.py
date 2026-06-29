"""Per-request context propagation.

A single contextvar holds the current request ID so that any code running
within a request — route handlers, services, the catch-all exception
handler, log records emitted from anywhere in the call stack — can attach
it without threading it through every function signature.
"""

from __future__ import annotations

import contextvars

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> str | None:
    """Return the current request's ID, or None outside a request context."""
    return _request_id_var.get()


def set_request_id(request_id: str) -> contextvars.Token:
    """Bind `request_id` to the current context. Returns a reset token."""
    return _request_id_var.set(request_id)


def reset_request_id(token: contextvars.Token) -> None:
    """Undo a prior set_request_id call using its token."""
    _request_id_var.reset(token)
