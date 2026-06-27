"""Centralized API versioning constants.

Every router prefix and the OAuth2 token URL previously hardcoded the
literal string "/api/v1" independently. Centralizing it here means bumping
the API version (e.g. introducing /api/v2 endpoints alongside /api/v1) is a
one-place change instead of a project-wide find-and-replace, and it removes
the risk of a typo silently producing a mismatched prefix in one router.

Importing this module and using API_V1_PREFIX must not change any existing
route's resolved path — it is a pure refactor of how the same "/api/v1"
string is spelled, not a behavior change.
"""

from __future__ import annotations

API_VERSION = "v1"
API_V1_PREFIX = f"/api/{API_VERSION}"
