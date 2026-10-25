"""Every API route must reject anonymous requests with 401, except the
explicitly public ones below. Sweeps the live route table, so a newly added
endpoint that forgets its auth dependency fails here."""

from fastapi.routing import APIRoute

from app.core.constants import API_V1_PREFIX
from app.main import app

PUBLIC = {
    f"{API_V1_PREFIX}/auth/register",
    f"{API_V1_PREFIX}/auth/login",
    f"{API_V1_PREFIX}/auth/refresh",
    f"{API_V1_PREFIX}/auth/logout",  # authenticated by the refresh token in its body
    f"{API_V1_PREFIX}/auth/forgot-password",
    f"{API_V1_PREFIX}/auth/reset-password",
}

DUMMY_ID = "00000000-0000-0000-0000-000000000000"


def _api_routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(API_V1_PREFIX):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


def test_sweep_finds_routes():
    assert len(list(_api_routes())) > 30


def test_every_non_public_api_route_requires_authentication(client):
    unprotected = []
    for method, path in _api_routes():
        if path in PUBLIC:
            continue
        url = path
        for param in [p for p in path.split("/") if p.startswith("{")]:
            url = url.replace(param, DUMMY_ID)
        response = client.request(method, url)
        if response.status_code != 401:
            unprotected.append(f"{method} {path} -> {response.status_code}")
    assert not unprotected, "Routes reachable without a token:\n" + "\n".join(unprotected)


def test_forged_bearer_token_is_rejected(client):
    response = client.get(
        f"{API_V1_PREFIX}/auth/me", headers={"Authorization": "Bearer forged.token.value"}
    )
    assert response.status_code == 401
