import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def efficiency_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 2001, "name": "Brattli AS"}]})

        if request.method == "GET" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"values": []})

        if request.method == "GET" and request.url.path == "/v2/employee":
            email = request.url.params.get("email")
            if email == "goncalo.oliveira@example.org":
                return httpx.Response(
                    200,
                    json={
                        "values": [
                            {
                                "id": 1001,
                                "firstName": "Goncalo",
                                "lastName": "Oliveira",
                                "email": "goncalo.oliveira@example.org",
                                "employments": [{"id": 1}],
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/order":
            recorded["order_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            recorded["invoice_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "PUT" and request.url.path == "/v2/invoice/6001/:payment":
            recorded["invoice_payment_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "POST" and request.url.path == "/v2/project":
            recorded.setdefault("project_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": 4001}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_invoice_workflow_avoids_unnecessary_product_lookup_for_description_only_prompt() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: efficiency_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.",
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
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Skylagring"
    assert "product" not in recorded["order_payload"]["orderLines"][0]
    assert "sendByEmail" not in recorded["invoice_payload"]
    app.dependency_overrides.clear()


def test_project_workflow_succeeds_with_single_project_post_and_no_trial_and_error() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: efficiency_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Crie o projeto "Implementação Rio" vinculado ao cliente Rio Azul Lda (org. nº 827937223). O gerente de projeto é Gonçalo Oliveira (goncalo.oliveira@example.org).',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "GET /v2/customer",
        "GET /v2/employee",
        "POST /v2/project",
    ]
    assert len(recorded["project_payloads"]) == 1
    assert recorded["project_payloads"][0]["projectManager"]["id"] == 1001
    app.dependency_overrides.clear()


def test_payment_workflow_keeps_same_call_count_and_carries_payment_fields() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: efficiency_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "GET /v2/customer",
        "POST /v2/order",
        "POST /v2/invoice",
        "PUT /v2/invoice/6001/:payment",
    ]
    assert "markAsPaid" not in recorded["invoice_payload"]
    assert recorded["invoice_payment_payload"]["paymentDate"] is not None
    assert recorded["invoice_payment_payload"]["amountPaidCurrency"] == 32200.0
    app.dependency_overrides.clear()


def test_invoice_with_product_name_only_uses_description_and_avoids_product_creation() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: efficiency_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Create invoice for customer "Brattli AS" with product "Consulting" 1500',
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
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Consulting"
    assert "product" not in recorded["order_payload"]["orderLines"][0]
    app.dependency_overrides.clear()


def test_invoice_with_name_only_customer_does_not_create_customer_prerequisite() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: efficiency_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Create invoice for customer "Unknown Name" with product "Consulting" 1500',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 502
    assert recorded["calls"] == [
        "GET /v2/customer",
    ]
    assert "order_payload" not in recorded
    assert "invoice_payload" not in recorded
    app.dependency_overrides.clear()
