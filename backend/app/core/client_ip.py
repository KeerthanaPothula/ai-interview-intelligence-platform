"""Client IP resolution shared by rate limiting and security logging."""

from __future__ import annotations

from fastapi import Request

from app.config import get_settings


def get_client_ip(request: Request) -> str:
    """Return the caller's IP address.

    Uses the TCP peer address unless TRUSTED_PROXY_COUNT is set, in which
    case the client is the Nth entry from the right of X-Forwarded-For (see
    the setting's comment for why the right side, not the left).
    """
    peer = request.client.host if request.client else "unknown"
    trusted_hops = get_settings().TRUSTED_PROXY_COUNT
    if trusted_hops <= 0:
        return peer

    forwarded = [
        hop.strip()
        for hop in request.headers.get("x-forwarded-for", "").split(",")
        if hop.strip()
    ]
    if len(forwarded) >= trusted_hops:
        return forwarded[-trusted_hops]
    return peer
