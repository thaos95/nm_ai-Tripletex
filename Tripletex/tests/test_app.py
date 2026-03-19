import base64
import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport
from app.config import settings


def mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v2/department":
            return httpx.Response(200, json={"values": [{"id": 838148, "name": "Avdeling"}]})

        if request.method == "POST" and request.url.path == "/v2/employee":
            return httpx.Response(200, json={"value": {"id": 1001}})

        if request.method == "GET" and request.url.path == "/v2/employee":
            first_name = request.url.params.get("firstName")
            last_name = request.url.params.get("lastName")
            if first_name == "Marte" and last_name == "Solberg":
                return httpx.Response(
                    200,
                    json={"values": [{"id": 1001, "firstName": "Marte", "lastName": "Solberg"}]},
                )
            return httpx.Response(200, json={"values": []})

        if request.method == "PUT" and request.url.path == "/v2/employee/1001":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "GET" and request.url.path == "/v2/employee/1001":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "id": 1001,
                        "firstName": "Marte",
                        "lastName": "Solberg",
                        "dateOfBirth": "1990-01-01",
                    }
                },
            )

        if request.method == "GET" and request.url.path == "/v2/customer":
            name = request.url.params.get("name")
            fields = request.url.params.get("fields")
            if fields == "id,name,email,organizationNumber":
                return httpx.Response(
                    200,
                    json={"fullResultSize": 1, "values": [{"id": 2001, "name": "Acme AS", "organizationNumber": "849612913"}]},
                )
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

        if request.method == "GET" and request.url.path == "/v2/employee":
            if request.url.params.get("fields") == "id,firstName,lastName,email" and request.url.params.get("count") == "100":
                return httpx.Response(
                    200,
                    json={"fullResultSize": 1, "values": [{"id": 1001, "firstName": "Ola", "lastName": "Nordmann", "email": "ola@example.org"}]},
                )

        if request.method == "POST" and request.url.path == "/v2/project":
            return httpx.Response(200, json={"value": {"id": 4001}})

        if request.method == "POST" and request.url.path == "/v2/order":
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "GET" and request.url.path == "/v2/ledger/voucher/7":
            return httpx.Response(200, json={"value": {"id": 7}})

        if request.method == "DELETE" and request.url.path == "/v2/ledger/voucher/7":
            return httpx.Response(200, json={})

        if request.method == "GET" and request.url.path == "/v2/travelExpense":
            return httpx.Response(200, json={"values": [{"id": 42}]})

        if request.method == "DELETE" and request.url.path == "/v2/travelExpense/42":
            return httpx.Response(200, json={})

        if request.method == "POST" and request.url.path == "/v2/travelExpense":
            payload = json.loads(request.content.decode("utf-8"))
            payload["id"] = 7001
            return httpx.Response(200, json={"value": payload})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"fullResultSize": 1, "values": [{"id": 1, "number": 1000, "name": "Kasse"}]})

        if request.method == "GET" and request.url.path == "/v2/ledger/posting":
            return httpx.Response(200, json={"fullResultSize": 1, "values": [{"id": 1, "date": "2026-01-10", "amount": 100.0}]})

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
    assert response.json() == {"status": "completed"}
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
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_list_employees() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Hent ansatte",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_search_customers() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Finn alle kunder med orgnr 849612913",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_update_employee() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Oppdater ansatt Marte Solberg med telefon +47 41234567",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
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
    assert response.json() == {"status": "completed"}
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
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_create_travel_expense() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett reiseregning 2026-03-19 med belop 450",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_delete_voucher() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Slett bilag 7",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_rejects_empty_prompt() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "   ",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_solve_rejects_non_https_base_url() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett kunde Acme AS",
            "files": [],
            "tripletex_credentials": {
                "base_url": "http://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_solve_rejects_empty_session_token() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett kunde Acme AS",
            "files": [],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "   ",
            },
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_solve_rejects_invalid_base64_file() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett kunde Acme AS",
            "files": [
                {
                    "filename": "bad.pdf",
                    "mime_type": "application/pdf",
                    "content_base64": "not-base64!!!",
                }
            ],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_solve_accepts_multiple_attachments() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Slett reiseregning 42",
            "files": [
                {
                    "filename": "invoice.pdf",
                    "mime_type": "application/pdf",
                    "content_base64": base64.b64encode(b"%PDF-1.4 test").decode("ascii"),
                },
                {
                    "filename": "receipt.png",
                    "mime_type": "image/png",
                    "content_base64": base64.b64encode(b"\x89PNG test").decode("ascii"),
                },
            ],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    app.dependency_overrides.clear()


def test_solve_rejects_missing_api_key_when_configured() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    original_api_key = settings.api_key
    settings.api_key = "secret-key"
    try:
        response = client.post(
            "/solve",
            json={
                "prompt": "Opprett kunde Acme AS, acme@example.org",
                "files": [],
                "tripletex_credentials": {
                    "base_url": "https://tx-proxy.ainm.no/v2",
                    "session_token": "token",
                },
            },
        )
    finally:
        settings.api_key = original_api_key
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_solve_rejects_wrong_api_key_when_configured() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    original_api_key = settings.api_key
    settings.api_key = "secret-key"
    try:
        response = client.post(
            "/solve",
            headers={"Authorization": "Bearer wrong-key"},
            json={
                "prompt": "Opprett kunde Acme AS, acme@example.org",
                "files": [],
                "tripletex_credentials": {
                    "base_url": "https://tx-proxy.ainm.no/v2",
                    "session_token": "token",
                },
            },
        )
    finally:
        settings.api_key = original_api_key
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_solve_accepts_correct_api_key_when_configured() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    original_api_key = settings.api_key
    settings.api_key = "secret-key"
    try:
        response = client.post(
            "/solve",
            headers={"Authorization": "Bearer secret-key"},
            json={
                "prompt": "Opprett kunde Acme AS, acme@example.org",
                "files": [],
                "tripletex_credentials": {
                    "base_url": "https://tx-proxy.ainm.no/v2",
                    "session_token": "token",
                },
            },
        )
    finally:
        settings.api_key = original_api_key
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}


def test_solve_only_accepts_post() -> None:
    client = TestClient(app)
    response = client.get("/solve")
    assert response.status_code == 405


def test_solve_rejects_invalid_json_body() -> None:
    client = TestClient(app)
    response = client.post(
        "/solve",
        data="{bad json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
