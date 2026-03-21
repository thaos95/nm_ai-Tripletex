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

        if request.method == "GET" and request.url.path == "/v2/invoice":
            recorded["credit_note_invoice_query"] = dict(request.url.params)
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 6001,
                            "customer": {"id": 2001},
                            "description": "Konsulenttimar",
                            "amountExcludingVatCurrency": 16200.0,
                        }
                    ]
                },
            )

        if request.method == "PUT" and request.url.path == "/v2/invoice/6001/:createCreditNote":
            recorded["credit_note_response"] = {"id": 6101}
            return httpx.Response(200, json={"value": {"id": 6101}})

        if request.method == "POST" and request.url.path == "/v2/project":
            recorded.setdefault("project_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": 4001}})

        if request.method == "POST" and request.url.path == "/v2/ledger/accountingDimensionName":
            recorded["dimension_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 8001}})

        if request.method == "POST" and request.url.path == "/v2/ledger/accountingDimensionValue":
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
        "GET /v2/invoice",
        "PUT /v2/invoice/6001/:createCreditNote",
    ]
    assert recorded["credit_note_invoice_query"]["invoiceDateFrom"] is not None
    assert recorded["credit_note_invoice_query"]["invoiceDateTo"] is not None
    assert recorded["credit_note_response"]["id"] == 6101
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
    assert recorded["invoice_payloads"][0] == {
        "invoiceDate": recorded["invoice_payloads"][0]["invoiceDate"],
        "invoiceDueDate": recorded["invoice_payloads"][0]["invoiceDueDate"],
        "customer": {"id": 2001},
        "orders": [{"id": 5001}],
    }
    app.dependency_overrides.clear()


def test_german_project_billing_prompt_keeps_invoice_due_date() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: advanced_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Erfassen Sie 32 Stunden für Hannah Richter (hannah.richter@example.org) auf der Aktivität "Design" im Projekt "E-Commerce-Entwicklung" für Bergwerk GmbH (Org.-Nr. 920065007). Stundensatz: 1550 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf den erfassten Stunden.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"][0] == "GET /v2/customer"
    assert recorded["calls"][-3:] == [
        "POST /v2/project",
        "POST /v2/order",
        "POST /v2/invoice",
    ]
    assert recorded["project_payloads"][0]["name"] == "E-Commerce-Entwicklung"
    assert recorded["order_payloads"][0]["orderLines"][0]["description"] == "Design"
    assert recorded["invoice_payloads"][0] == {
        "invoiceDate": recorded["invoice_payloads"][0]["invoiceDate"],
        "invoiceDueDate": recorded["invoice_payloads"][0]["invoiceDueDate"],
        "customer": {"id": 2001},
        "orders": [{"id": 5001}],
    }
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
        "POST /v2/ledger/accountingDimensionName",
        "POST /v2/ledger/accountingDimensionValue",
        "POST /v2/ledger/accountingDimensionValue",
        "POST /v2/ledger/voucher",
    ]
    assert recorded["dimension_payload"]["dimensionName"] == "Marked"
    assert recorded["dimension_value_payloads"][0]["description"] == "Bedrift"
    assert recorded["voucher_payloads"][0]["postings"][0]["account"]["number"] == 6590
    assert "freeAccountingDimension1" in recorded["voucher_payloads"][0]["postings"][0]
    app.dependency_overrides.clear()


def test_payroll_voucher_workflow_is_blocked_before_manual_voucher_fallback() -> None:
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

    assert response.status_code == 502
    assert "payroll voucher fallback is not supported safely" in response.json()["detail"].lower()
    assert recorded.get("calls", []) == []
    app.dependency_overrides.clear()
