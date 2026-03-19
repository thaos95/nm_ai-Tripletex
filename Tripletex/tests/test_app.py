import base64
import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v2/department":
            return httpx.Response(200, json={"values": [{"id": 838148, "name": "Avdeling"}]})

        if request.method == "POST" and request.url.path == "/v2/employee":
            return httpx.Response(200, json={"value": {"id": 1001}})

        if request.method == "GET" and request.url.path == "/v2/customer":
            name = request.url.params.get("name")
            if name == "Acme AS":
                return httpx.Response(
                    200,
                    json={"values": [{"id": 2001, "name": "Acme AS", "phoneNumber": "000"}]},
                )
            return httpx.Response(200, json={"values": []})

        if request.method == "PUT" and request.url.path == "/v2/customer/2001":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "POST" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"value": {"id": 2002}})

        if request.method == "GET" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"value": {"id": 3001}})

        if request.method == "POST" and request.url.path == "/v2/project":
            return httpx.Response(200, json={"value": {"id": 4001}})

        if request.method == "POST" and request.url.path == "/v2/order":
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "GET" and request.url.path == "/v2/travelExpense":
            return httpx.Response(200, json={"values": [{"id": 42}]})

        if request.method == "DELETE" and request.url.path == "/v2/travelExpense/42":
            return httpx.Response(200, json={})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_solve_create_employee() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal vaere kontoadministrator.",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["task_type"] == "create_employee"
    assert response.json()["operations"] == 2
    app.dependency_overrides.clear()


def test_solve_update_customer() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Oppdater kunde Acme AS med telefon +47 12345678",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "update_customer"
    assert response.json()["operations"] == 1
    app.dependency_overrides.clear()


def test_solve_create_invoice_with_prerequisites() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Create invoice for customer "Acme AS" with product "Consulting" 1500',
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "create_invoice"
    assert response.json()["operations"] >= 3
    app.dependency_overrides.clear()


def test_solve_with_attachment_and_delete_travel_expense() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Slett reiseregning 42",
            "files": [
                {
                    "filename": "note.txt",
                    "mime_type": "text/plain",
                    "content_base64": base64.b64encode(b"hello").decode("ascii"),
                }
            ],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "delete_travel_expense"
    assert response.json()["operations"] == 1
    app.dependency_overrides.clear()
