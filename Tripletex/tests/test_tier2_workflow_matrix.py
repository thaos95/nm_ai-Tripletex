import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def tier2_transport(recorded: dict) -> httpx.MockTransport:
    customers = {
        "845762686": {"id": 2001, "name": "Brattli AS"},
        "830362894": {"id": 2002, "name": "Windmill Ltd"},
        "916058896": {"id": 2003, "name": "Floresta Lda"},
        "831075392": {"id": 2004, "name": "Dorada SL"},
        "827937223": {"id": 2005, "name": "Rio Azul Lda"},
    }
    customers_by_name = {
        "brattli as": customers["845762686"],
        "windmill ltd": customers["830362894"],
        "floresta lda": customers["916058896"],
        "dorada sl": customers["831075392"],
        "rio azul lda": customers["827937223"],
    }
    employees_by_email = {
        "isabel.rodriguez@example.org": {
            "id": 1001,
            "firstName": "Isabel",
            "lastName": "Rodriguez",
            "email": "isabel.rodriguez@example.org",
            "employments": [{"id": 1}],
        },
        "goncalo.oliveira@example.org": {
            "id": 1002,
            "firstName": "Goncalo",
            "lastName": "Oliveira",
            "email": "goncalo.oliveira@example.org",
            "employments": [{"id": 2}],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/customer":
            org_number = request.url.params.get("organizationNumber")
            name = (request.url.params.get("name") or "").strip().lower()
            if org_number and org_number in customers:
                return httpx.Response(200, json={"values": [customers[org_number]]})
            if name and name in customers_by_name:
                return httpx.Response(200, json={"values": [customers_by_name[name]]})
            return httpx.Response(200, json={"values": []})

        if request.method == "GET" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"values": []})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"values": [{"id": 3501, "number": 3000, "name": "Salgsinntekt"}]})

        if request.method == "GET" and request.url.path == "/v2/employee":
            email = (request.url.params.get("email") or "").strip().lower()
            if email in employees_by_email:
                return httpx.Response(200, json={"values": [employees_by_email[email]]})
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/order":
            recorded["order_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            recorded["invoice_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "PUT" and request.url.path == "/v2/invoice/6001/:payment":
            recorded["invoice_payment_payload"] = dict(request.url.params)
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "POST" and request.url.path == "/v2/project":
            recorded["project_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 7001}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    ("prompt", "expected_calls", "expected_order_description", "payment_expected"),
    [
        (
            "Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) pa 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.",
            ["GET /v2/customer", "POST /v2/order", "POST /v2/invoice"],
            "Skylagring",
            False,
        ),
        (
            'The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.',
            ["GET /v2/customer", "POST /v2/order", "POST /v2/invoice", "PUT /v2/invoice/6001/:payment"],
            "System Development",
            True,
        ),
        (
            'O cliente Floresta Lda (org. no 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.',
            ["GET /v2/customer", "POST /v2/order", "POST /v2/invoice", "PUT /v2/invoice/6001/:payment"],
            "Desenvolvimento de sistemas",
            True,
        ),
    ],
)
def test_tier2_invoice_and_payment_workflow_matrix(
    prompt: str,
    expected_calls: list,
    expected_order_description: str,
    payment_expected: bool,
) -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: tier2_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": prompt,
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == expected_calls
    assert recorded["order_payload"]["orderLines"][0]["description"] == expected_order_description
    assert "product" not in recorded["order_payload"]["orderLines"][0]
    if payment_expected:
        assert "markAsPaid" not in recorded["invoice_payload"]
        assert recorded["invoice_payment_payload"]["paymentDate"] is not None
        assert recorded["invoice_payment_payload"]["paidAmount"] is not None
        assert recorded["invoice_payment_payload"]["amountPaidCurrency"] is not None
        assert recorded["invoice_payment_payload"]["paymentTypeId"] == "6"
    else:
        assert "markAsPaid" not in recorded["invoice_payload"]
        assert "paymentDate" not in recorded["invoice_payload"]
        assert "amountPaidCurrency" not in recorded["invoice_payload"]
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("prompt", "expected_customer_id", "expected_manager_id"),
    [
        (
            'Crea el proyecto "Implementacion Dorada" vinculado al cliente Dorada SL (org. no 831075392). El director del proyecto es Isabel Rodriguez (isabel.rodriguez@example.org).',
            2004,
            1001,
        ),
        (
            'Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).',
            2005,
            1002,
        ),
    ],
)
def test_tier2_project_workflow_matrix(
    prompt: str,
    expected_customer_id: int,
    expected_manager_id: int,
) -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: tier2_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": prompt,
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
    assert recorded["project_payload"]["customer"]["id"] == expected_customer_id
    assert recorded["project_payload"]["projectManager"]["id"] == expected_manager_id
    app.dependency_overrides.clear()
