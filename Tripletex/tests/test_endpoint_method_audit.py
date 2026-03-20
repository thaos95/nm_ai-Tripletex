import json
from typing import Set

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def audit_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        recorded.setdefault("calls", []).append(f"{request.method} {request.url.path}")

        if request.method == "GET" and request.url.path == "/v2/department":
            return httpx.Response(200, json={"values": [{"id": 1, "name": "Main"}]})

        if request.method == "GET" and request.url.path == "/v2/customer":
            name = request.url.params.get("name")
            org = request.url.params.get("organizationNumber")
            fields = request.url.params.get("fields")
            if fields == "id,name,email,organizationNumber":
                return httpx.Response(200, json={"values": [{"id": 2001, "name": "Acme AS"}]})
            if name == "Acme AS" or org == "845762686":
                return httpx.Response(200, json={"values": [{"id": 2001, "name": "Acme AS", "phoneNumber": "000"}]})
            return httpx.Response(200, json={"values": []})

        if request.method == "GET" and request.url.path == "/v2/customer/2001":
            return httpx.Response(200, json={"value": {"id": 2001, "name": "Acme AS", "phoneNumber": "000"}})

        if request.method == "POST" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"value": {"id": 2002}})

        if request.method == "PUT" and request.url.path == "/v2/customer/2001":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "GET" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"value": {"id": 3001}})

        if request.method == "GET" and request.url.path == "/v2/employee":
            email = request.url.params.get("email")
            fields = request.url.params.get("fields")
            if fields == "id,firstName,lastName,email":
                return httpx.Response(200, json={"values": [{"id": 1001, "firstName": "Ola", "lastName": "Nordmann", "email": "ola@example.org"}]})
            if email == "marte@example.org":
                return httpx.Response(200, json={"values": [{"id": 1001, "firstName": "Marte", "lastName": "Solberg"}]})
            return httpx.Response(200, json={"values": []})

        if request.method == "GET" and request.url.path == "/v2/employee/1001":
            return httpx.Response(200, json={"value": {"id": 1001, "firstName": "Marte", "lastName": "Solberg"}})

        if request.method == "POST" and request.url.path == "/v2/employee":
            return httpx.Response(200, json={"value": {"id": 1001}})

        if request.method == "PUT" and request.url.path == "/v2/employee/1001":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "POST" and request.url.path == "/v2/project":
            return httpx.Response(200, json={"value": {"id": 4001}})

        if request.method == "POST" and request.url.path == "/v2/order":
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "POST" and request.url.path == "/v2/department":
            return httpx.Response(200, json={"value": {"id": 7001}})

        if request.method == "GET" and request.url.path == "/v2/travelExpense":
            return httpx.Response(200, json={"values": [{"id": 42}]})

        if request.method == "GET" and request.url.path == "/v2/travelExpense/42":
            return httpx.Response(200, json={"value": {"id": 42, "date": "2026-03-18", "amount": 450.0}})

        if request.method == "POST" and request.url.path == "/v2/travelExpense":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "PUT" and request.url.path == "/v2/travelExpense/42":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "DELETE" and request.url.path == "/v2/travelExpense/42":
            return httpx.Response(200, json={})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"values": [{"id": 1, "number": 1000, "name": "Kasse"}]})

        if request.method == "GET" and request.url.path == "/v2/ledger/posting":
            return httpx.Response(200, json={"values": [{"id": 1, "date": "2026-01-10", "amount": 100.0}]})

        if request.method == "GET" and request.url.path == "/v2/ledger/voucher/7":
            return httpx.Response(200, json={"value": {"id": 7}})

        if request.method == "POST" and request.url.path == "/v2/ledger/voucher":
            return httpx.Response(200, json={"value": {"id": 9001}})

        if request.method == "DELETE" and request.url.path == "/v2/ledger/voucher/7":
            return httpx.Response(200, json={})

        if request.method == "POST" and request.url.path == "/v2/dimension":
            return httpx.Response(200, json={"value": {"id": 8001}})

        if request.method == "POST" and request.url.path == "/v2/dimension/value":
            return httpx.Response(200, json={"value": {"id": 8101}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    ("name", "prompt", "expected_methods"),
    [
        ("employee_get_post_put", "Oppdater ansatt Marte Solberg med e-post marte@example.org og telefon +47 41234567", {"GET /v2/employee", "GET /v2/employee/1001", "PUT /v2/employee/1001"}),
        ("customer_get_post_put", "Oppdater kunde Acme AS med telefon +47 12345678", {"GET /v2/customer", "PUT /v2/customer/2001"}),
        ("product_get_post", 'Opprett produktet "Analyserapport" med pris 18050 kr.', {"POST /v2/product"}),
        ("invoice_get_post", "Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.", {"GET /v2/customer", "POST /v2/order", "POST /v2/invoice"}),
        ("order_get_post", "Opprett ordre til kunden Brattli AS (org.nr 845762686) for Skylagring.", {"GET /v2/customer", "POST /v2/order"}),
        ("travel_get_post_put_delete", "Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19", {"GET /v2/travelExpense/42", "PUT /v2/travelExpense/42"}),
        ("travel_delete", "Slett reiseregning 42", {"DELETE /v2/travelExpense/42"}),
        ("project_get_post", 'Crea el proyecto "Implementación Dorada" vinculado al cliente Dorada SL (org. nº 831075392).', {"GET /v2/customer", "POST /v2/project"}),
        ("department_post", 'Opprett tre avdelingar i Tripletex: "Økonomi", "Administrasjon" og "Innkjøp".', {"POST /v2/department"}),
        ("ledger_account_get", "Vis kontoplan", {"GET /v2/ledger/account"}),
        ("ledger_posting_get", "Vis hovedboksposteringer", {"GET /v2/ledger/posting"}),
        ("ledger_voucher_get_post_delete", "Slett bilag 7", {"GET /v2/ledger/voucher/7", "DELETE /v2/ledger/voucher/7"}),
    ],
)
def test_endpoint_method_audit(name: str, prompt: str, expected_methods: Set[str]) -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: audit_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": prompt,
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200, name
    assert expected_methods.issubset(set(recorded["calls"])), name
    app.dependency_overrides.clear()
