import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport
from app.schemas import TaskType
from app.workflow import parse_workflow


def sequence_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/employee":
            email = request.url.params.get("email")
            if email == "jonas.haugen@example.org":
                return httpx.Response(
                    200,
                    json={"values": [{"id": 1001, "firstName": "Jonas", "lastName": "Haugen", "employments": [{"id": 1}]}]},
                )
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/customer":
            recorded["customer_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 2001}})

        if request.method == "POST" and request.url.path == "/v2/product":
            recorded["product_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 3001}})

        if request.method == "POST" and request.url.path == "/v2/project":
            recorded["project_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 4001}})

        if request.method == "POST" and request.url.path == "/v2/order":
            recorded.setdefault("order_payloads", []).append(json.loads(request.content.decode("utf-8")))
            order_id = 5000 + len(recorded["order_payloads"])
            return httpx.Response(200, json={"value": {"id": order_id}})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/ledger/account":
            recorded["ledger_account_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 3501, "number": recorded["ledger_account_payload"]["number"]}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            recorded["invoice_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "PUT" and request.url.path == "/v2/invoice/6001/:payment":
            recorded["invoice_payment_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 6001}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_parse_workflow_splits_explicit_multi_step_prompt() -> None:
    tasks, segments = parse_workflow(
        'Opprett kunde Acme AS, acme@example.org. Opprett produktet "Consulting" for 1500 kr. Opprett og send en faktura.'
    )

    assert len(segments) == 3
    assert [task.task_type for task in tasks] == [
        TaskType.CREATE_CUSTOMER,
        TaskType.CREATE_PRODUCT,
        TaskType.CREATE_INVOICE,
    ]


def test_parse_workflow_merges_followup_fragment_into_previous_task() -> None:
    tasks, segments = parse_workflow(
        'Opprett kunde Acme AS, acme@example.org. Opprett prosjektet "Implementering Tindra". Prosjektleder er Jonas Haugen (jonas.haugen@example.org).'
    )

    assert len(segments) == 2
    assert [task.task_type for task in tasks] == [
        TaskType.CREATE_CUSTOMER,
        TaskType.CREATE_PROJECT,
    ]
    assert tasks[1].related_entities["project_manager"]["email"] == "jonas.haugen@example.org"


def test_solve_multi_step_prompt_reuses_created_customer_and_product() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: sequence_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Opprett kunde Acme AS, acme@example.org. Opprett produktet "Consulting" for 1500 kr. Opprett og send en faktura.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "POST /v2/customer",
        "POST /v2/product",
        "POST /v2/order",
        "POST /v2/invoice",
    ]
    assert recorded["order_payloads"][0]["customer"]["id"] == 2001
    assert recorded["order_payloads"][0]["orderLines"][0]["product"]["id"] == 3001
    assert recorded["invoice_payload"]["customer"]["id"] == 2001
    assert recorded["invoice_payload"]["orders"] == [{"id": 5001}]
    app.dependency_overrides.clear()


def test_solve_customer_then_project_reuses_created_customer() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: sequence_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Opprett kunde Acme AS, acme@example.org. Opprett prosjektet "Implementering Tindra". Prosjektleder er Jonas Haugen (jonas.haugen@example.org).',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "POST /v2/customer",
        "GET /v2/employee",
        "POST /v2/project",
    ]
    assert recorded["project_payload"]["customer"]["id"] == 2001
    assert recorded["project_payload"]["projectManager"]["id"] == 1001
    app.dependency_overrides.clear()


def test_solve_order_then_invoice_payment_reuses_existing_order() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: sequence_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": 'Opprett kunde Acme AS, acme@example.org. Opprett produktet "Consulting" for 1500 kr. Opprett ordre. Opprett faktura og registrer full betaling.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert recorded["calls"] == [
        "POST /v2/customer",
        "POST /v2/product",
        "POST /v2/order",
        "POST /v2/invoice",
        "PUT /v2/invoice/6001/:payment",
    ]
    assert len(recorded["order_payloads"]) == 1
    assert recorded["invoice_payload"]["orders"] == [{"id": 5001}]
    assert "markAsPaid" not in recorded["invoice_payload"]
    assert recorded["invoice_payment_payload"]["amountPaidCurrency"] == 1500
    app.dependency_overrides.clear()
