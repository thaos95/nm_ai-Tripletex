import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def unauthorized_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status": 401, "message": "Unauthorized"})

    return httpx.MockTransport(handler)


def wrong_endpoint_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Wrong endpoint path")

    return httpx.MockTransport(handler)


def test_solve_returns_completed_on_tripletex_unauthorized_error() -> None:
    app.dependency_overrides[get_client_transport] = unauthorized_transport
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett kunde Acme AS, acme@example.org",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "wrong-token"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_returns_completed_on_tripletex_wrong_endpoint_error() -> None:
    app.dependency_overrides[get_client_transport] = wrong_endpoint_transport
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett kunde Acme AS, acme@example.org",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()
