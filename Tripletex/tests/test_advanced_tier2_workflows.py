import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def advanced_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/customer":
            org = request.url.params.get("organizationNumber")
            if org:
                return httpx.Response(200, json={"values": [{"id": 2001, "name": "Matched Customer"}]})
            return httpx.Response(200, json={"values": []})

        if request.method == "GET" and request.url.path == "/v2/employee":
            email = request.url.params.get("email")
            if email == "hilde.hansen@example.org":
                return httpx.Response(
                    200,
                    json={"values": [{"id": 1001, "firstName": "Hilde", "lastName": "Hansen", "employments": [{"id": 1}]}]},
                )
            if email == "james.williams@example.org":
                return httpx.Response(
                    200,
                    json={"values": [{"id": 1002, "firstName": "James", "lastName": "Williams", "employments": [{"id": 2}]}]},
                )
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/order":
            recorded.setdefault("order_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            recorded.setdefault("invoice_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "POST" and request.url.path == "/v2/project":
            recorded.setdefault("project_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": 4001}})

        if request.method == "POST" and request.url.path == "/v2/dimension":
            recorded["dimension_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 8001}})

        if request.method == "POST" and request.url.path == "/v2/dimension/value":
            recorded.setdefault("dimension_value_payloads", []).append(json.loads(request.content.decode("utf-8")))
            value_id = 8100 + len(recorded["dimension_value_payloads"])
            return httpx.Response(200, json={"value": {"id": value_id}})

        if request.method == "POST" and request.url.path == "/v2/ledger/voucher":
            recorded.setdefault("voucher_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": 9001}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_credit_note_workflow_creates_credit_invoice_payload() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: advanced_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Kunden Fossekraft AS (org.nr 918737227) har reklamert pa fakturaen for "Konsulenttimar" (16200 kr ekskl. MVA). Opprett ei fullstendig kreditnota som reverserer heile fakturaen.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "GET /v2/customer",
        "POST /v2/order",
        "POST /v2/invoice",
    ]
    assert recorded["invoice_payloads"][0]["creditNote"] is True
    app.dependency_overrides.clear()


def test_project_billing_workflow_creates_project_then_invoice() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: advanced_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Sett fastpris 203000 kr pa prosjektet "Digital transformasjon" for Stormberg AS (org.nr 834028719). Prosjektleder er Hilde Hansen (hilde.hansen@example.org). Fakturer kunden for 75 % av fastprisen som en delbetaling.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "GET /v2/customer",
        "GET /v2/employee",
        "POST /v2/project",
        "POST /v2/order",
        "POST /v2/invoice",
    ]
    assert recorded["project_payloads"][0]["projectManager"]["id"] == 1001
    app.dependency_overrides.clear()


def test_dimension_voucher_workflow_creates_dimension_values_and_voucher() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: advanced_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Crie uma dimensao contabilistica personalizada "Marked" com os valores "Bedrift" e "Privat". Em seguida, lance um documento na conta 6590 por 16750 NOK, vinculado ao valor de dimensao "Bedrift".',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "POST /v2/dimension",
        "POST /v2/dimension/value",
        "POST /v2/dimension/value",
        "POST /v2/ledger/voucher",
    ]
    assert recorded["dimension_payload"]["name"] == "Marked"
    assert recorded["voucher_payloads"][0]["voucherLines"][0]["account"]["number"] == "6590"
    app.dependency_overrides.clear()


def test_payroll_voucher_workflow_uses_manual_voucher_fallback() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: advanced_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": "Run payroll for James Williams (james.williams@example.org) for this month. The base salary is 34950 NOK. Add a one-time bonus of 15450 NOK on top of the base salary. If the salary API is unavailable, you can use manual vouchers on salary accounts (5000-series) to record the payroll expense.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "GET /v2/employee",
        "POST /v2/ledger/voucher",
    ]
    voucher_payload = recorded["voucher_payloads"][0]
    assert voucher_payload["employee"]["id"] == 1002
    assert voucher_payload["voucherLines"][0]["account"]["number"] == "5000"
    assert voucher_payload["voucherLines"][0]["amount"] == 50400.0
    app.dependency_overrides.clear()
