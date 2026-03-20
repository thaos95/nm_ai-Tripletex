import base64
import json
from datetime import date

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport
from app.config import settings


TODAY_ISO = date.today().isoformat()


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

        if request.method == "GET" and request.url.path == "/v2/travelExpense/42":
            return httpx.Response(200, json={"value": {"id": 42, "date": "2026-03-18", "amount": 450.0}})

        if request.method == "PUT" and request.url.path == "/v2/travelExpense/42":
            payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": payload})

        if request.method == "GET" and request.url.path == "/v2/ledger/account":
            return httpx.Response(200, json={"fullResultSize": 1, "values": [{"id": 1, "number": 1000, "name": "Kasse"}]})

        if request.method == "GET" and request.url.path == "/v2/ledger/posting":
            return httpx.Response(200, json={"fullResultSize": 1, "values": [{"id": 1, "date": "2026-01-10", "amount": 100.0}]})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def recording_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v2/department":
            return httpx.Response(200, json={"values": [{"id": 1, "name": "Main"}]})

        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 2001, "name": "Acme AS"}]})

        if request.method == "GET" and request.url.path == "/v2/product":
            return httpx.Response(200, json={"values": []})

        if request.method == "POST" and request.url.path == "/v2/customer":
            recorded["customer_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 2001}})

        if request.method == "POST" and request.url.path == "/v2/product":
            recorded["product_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 3001}})

        if request.method == "POST" and request.url.path == "/v2/employee":
            recorded["employee_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 1001}})

        if request.method == "POST" and request.url.path == "/v2/order":
            recorded["order_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 5001}})

        if request.method == "POST" and request.url.path == "/v2/invoice":
            recorded["invoice_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 6001}})

        if request.method == "POST" and request.url.path == "/v2/department":
            recorded.setdefault("department_payloads", []).append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"value": {"id": len(recorded["department_payloads"])}})

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


def test_inspect_returns_parsed_task_plan_and_warnings() -> None:
    client = TestClient(app)
    response = client.post(
        "/inspect",
        json={
            "prompt": 'Erfassen Sie 32 Stunden für Hannah Richter (hannah.richter@example.org) auf der Aktivität "Design" im Projekt "E-Commerce-Entwicklung" für Bergwerk GmbH (Org.-Nr. 920065007). Stundensatz: 1550 NOK/h. Erstellen Sie eine Projektrechnung an den Kunden basierend auf den erfassten Stunden.',
            "files": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_task"]["task_type"] == "create_project_billing"
    assert body["parsed_task"]["fields"]["name"] == "E-Commerce-Entwicklung"
    assert body["parsed_task"]["related_entities"]["order"]["description"] == "Design"
    assert body["plan"][-1] == {
        "name": "create-billing-invoice",
        "resource": "invoice",
        "action": "create",
    }
    assert body["warnings"] == ["Dropped unsupported field 'email' for task create_project_billing"]
    assert body["blocking_error"] is None


def test_inspect_invoice_prompt_omits_send_flag_and_product_resolution_when_description_is_enough() -> None:
    client = TestClient(app)
    response = client.post(
        "/inspect",
        json={
            "prompt": "Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.",
            "files": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_task"]["task_type"] == "create_invoice"
    assert "sendByEmail" not in body["parsed_task"]["fields"]
    assert [step["name"] for step in body["plan"]] == [
        "resolve-invoice-customer",
        "create-order",
        "create-invoice",
    ]


def test_inspect_update_travel_expense_prompt() -> None:
    client = TestClient(app)
    response = client.post(
        "/inspect",
        json={
            "prompt": "Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19",
            "files": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_task"]["task_type"] == "update_travel_expense"
    assert body["parsed_task"]["fields"]["travel_expense_id"] == 42
    assert body["parsed_task"]["fields"]["amount"] == 950.0
    assert [step["name"] for step in body["plan"]] == [
        "find-travel-expense",
        "update-travel-expense",
    ]


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


def test_solve_update_travel_expense() -> None:
    app.dependency_overrides[get_client_transport] = mock_transport
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Oppdater reiseregning 42 med beløp 950 og dato 2026-03-19",
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


def test_solve_create_customer_preserves_supplier_and_address_fields() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Registrer leverandøren Dalheim AS med organisasjonsnummer 892196753. Adressa er Parkveien 45, 5003 Bergen. E-post: faktura@dalheim.no.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["customer_payload"]["isSupplier"] is True
    assert recorded["customer_payload"]["organizationNumber"] == "892196753"
    assert "address" not in recorded["customer_payload"]
    assert "postalCode" not in recorded["customer_payload"]
    assert "city" not in recorded["customer_payload"]
    app.dependency_overrides.clear()


def test_solve_create_employee_preserves_birth_and_start_dates() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Wir haben einen neuen Mitarbeiter namens Leonie Becker, geboren am 17. January 1996. Bitte legen Sie ihn als Mitarbeiter mit der E-Mail leonie.becker@example.org und dem Startdatum 12. January 2026 an.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["employee_payload"]["dateOfBirth"] == "1996-01-17"
    assert "dateFrom" not in recorded["employee_payload"]
    app.dependency_overrides.clear()


def test_solve_create_employee_omits_proxy_invalid_start_date_field() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Me har ein ny tilsett som heiter Geir Stolsvik, fodd 6. March 1990. Opprett vedkomande som tilsett med e-post geir.stlsvik@example.org og startdato 14. November 2026.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["employee_payload"]["dateOfBirth"] == "1990-03-06"
    assert "dateFrom" not in recorded["employee_payload"]
    app.dependency_overrides.clear()


def test_solve_create_product_preserves_number_and_vat() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Opprett produktet "Havregryn" med produktnummer 3113. Prisen er 29250 kr eksklusiv MVA, og MVA-sats for næringsmiddel på 15 % skal nyttast.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["product_payload"]["name"] == "Havregryn"
    assert recorded["product_payload"]["priceExcludingVatCurrency"] == 29250
    assert "productNumber" not in recorded["product_payload"]
    assert "vatPercentage" not in recorded["product_payload"]
    app.dependency_overrides.clear()


def test_solve_create_invoice_uses_description_when_product_missing() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Créez et envoyez une facture au client Étoile SARL (nº org. 995085488) de 7250 NOK hors TVA. La facture concerne Rapport d'analyse.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Rapport d'analyse"
    assert recorded["order_payload"]["orderDate"] == TODAY_ISO
    assert recorded["order_payload"]["deliveryDate"] == TODAY_ISO
    assert recorded["invoice_payload"]["invoiceDate"] == TODAY_ISO
    assert "sendByEmail" not in recorded["invoice_payload"]
    app.dependency_overrides.clear()


def test_solve_spanish_invoice_uses_description_phrase() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Crea y envía una factura al cliente Montaña SL (org. nº 831306742) por 48600 NOK sin IVA. La factura es por Licencia de software.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Licencia de software"
    app.dependency_overrides.clear()


def test_solve_payment_prompt_is_not_unsupported() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
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
    assert recorded["order_payload"]["orderLines"][0]["description"] == "System Development"
    assert recorded["invoice_payload"]["invoiceDate"] == TODAY_ISO
    assert recorded["invoice_payload"]["markAsPaid"] is True
    assert recorded["invoice_payload"]["paymentDate"] == TODAY_ISO
    assert recorded["invoice_payload"]["amountPaidCurrency"] == 32200.0
    app.dependency_overrides.clear()


def test_solve_portuguese_payment_prompt_is_not_unsupported() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'O cliente Floresta Lda (org. nº 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Desenvolvimento de sistemas"
    assert recorded["invoice_payload"]["invoiceDate"] == TODAY_ISO
    assert recorded["invoice_payload"]["markAsPaid"] is True
    assert recorded["invoice_payload"]["paymentDate"] == TODAY_ISO
    assert recorded["invoice_payload"]["amountPaidCurrency"] == 30450.0
    app.dependency_overrides.clear()


def test_solve_nynorsk_invoice_uses_description_without_quotes() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Opprett og send ein faktura til kunden Strandvik AS (org.nr 993504815) på 1800 kr eksklusiv MVA. Fakturaen gjeld Opplæring.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Opplæring"
    app.dependency_overrides.clear()


def test_solve_create_multiple_departments() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Erstellen Sie drei Abteilungen in Tripletex: "Utvikling", "Innkjøp" und "Økonomi".',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert [item["name"] for item in recorded["department_payloads"]] == ["Utvikling", "Innkjøp", "Økonomi"]
    app.dependency_overrides.clear()
def test_solve_payment_reversal_prompt_creates_outstanding_invoice() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Betalinga frÃ¥ Strandvik AS (org.nr 859256333) for fakturaen "Nettverksteneste" (41550 kr ekskl. MVA) vart returnert av banken. Reverser betalinga slik at fakturaen igjen viser utestÃ¥ande belÃ¸p.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Nettverksteneste"
    assert "markAsPaid" not in recorded["invoice_payload"]
    assert "paymentDate" not in recorded["invoice_payload"]
    app.dependency_overrides.clear()


def test_solve_multiline_order_invoice_payment_prompt_builds_multiple_order_lines() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Erstellen Sie einen Auftrag fÃ¼r den Kunden Waldstein GmbH (Org.-Nr. 899060113) mit den Produkten Netzwerkdienst (5411) zu 29200 NOK und Schulung (7883) zu 10350 NOK. Wandeln Sie den Auftrag in eine Rechnung um und registrieren Sie die vollstÃ¤ndige Zahlung.',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert len(recorded["order_payload"]["orderLines"]) == 2
    assert recorded["order_payload"]["orderLines"][0]["description"] == "Netzwerkdienst"
    assert recorded["order_payload"]["orderLines"][1]["description"] == "Schulung"
    assert recorded["invoice_payload"]["markAsPaid"] is True
    assert recorded["invoice_payload"]["amountPaidCurrency"] == 39550.0
    app.dependency_overrides.clear()
