"""Reusable pagination dependency for list endpoints.

Extracted from the skip/limit Query parameters that interviews.list_sessions
already used, so any future paginated list endpoint can depend on the same
validated, documented skip/limit pair instead of redeclaring it inline.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class PaginationParams:
    skip: int
    limit: int


def pagination_params(
    skip: int = Query(default=0, ge=0, description="Number of records to skip."),
    limit: int = Query(
        default=20, ge=1, le=100, description="Maximum records to return."
    ),
) -> PaginationParams:
    return PaginationParams(skip=skip, limit=limit)
