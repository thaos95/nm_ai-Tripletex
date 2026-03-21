import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def retry_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 2001, "name": "Brattli AS"}]})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"values": [{"id": 3501, "number": 3000, "name": "Salgsinntekt"}]})

        if request.method == "POST" and request.url.path == "/v2/order":
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            payload = json.loads(request.content.decode("utf-8"))
            recorded.setdefault("invoice_payloads", []).append(payload)
            if len(recorded["invoice_payloads"]) == 1:
                return httpx.Response(
                    422,
                    json={
                        "status": 422,
                        "message": "Request mapping failed",
                        "validationMessages": [
                            {"field": "invoiceDueDate", "message": "Unexpected field mapping"}
                        ],
                    },
                )
            return httpx.Response(200, json={"value": {"id": 6001}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def bank_error_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 2001, "name": "Brattli AS"}]})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"values": [{"id": 3501, "number": 3000, "name": "Salgsinntekt"}]})

        if request.method == "POST" and request.url.path == "/v2/order":
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            recorded.setdefault("invoice_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                422,
                json={
                    "status": 422,
                    "code": 18000,
                    "message": "Validering feilet.",
                    "validationMessages": [
                        {"field": None, "message": "Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer."}
                    ],
                },
            )

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_create_invoice_retries_once_with_minimal_payload_on_generic_422() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: retry_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Opprett en faktura til kunden Brattli AS (org.nr 845762686) for "Skylagring" pa 26450 kr eksklusiv MVA.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "GET /v2/customer",
        "POST /v2/order",
        "POST /v2/invoice",
        "POST /v2/invoice",
    ]
    assert "invoiceDueDate" in recorded["invoice_payloads"][0]
    assert recorded["invoice_payloads"][1] == {
        "invoiceDate": recorded["invoice_payloads"][1]["invoiceDate"],
        "customer": {"id": 2001},
        "orders": [{"id": 5001}],
    }
    app.dependency_overrides.clear()


def test_create_invoice_does_not_retry_on_bank_account_validation_error() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: bank_error_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Opprett en faktura til kunden Brattli AS (org.nr 845762686) for "Skylagring" pa 26450 kr eksklusiv MVA.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 424
    detail = response.json()["detail"]
    assert detail["stage"] == "invoice_creation"
    assert detail["issue"] == "company_bank_account_required"
    assert detail["task_type"] == "create_invoice"
    assert recorded["calls"] == [
        "GET /v2/customer",
        "POST /v2/order",
        "POST /v2/invoice",
    ]
    assert len(recorded["invoice_payloads"]) == 1
    app.dependency_overrides.clear()
