from datetime import date
from typing import Set

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_client_transport
from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task

from tests.test_app import recording_transport

TODAY_ISO = date.today().isoformat()


@pytest.mark.parametrize(
    ("prompt", "task_type", "field_expectations", "related_expectations"),
    [
        (
            "Registe o fornecedor Solmar Lda com numero de organizacao 978911226. E-mail: faktura@solmarlda.no.",
            TaskType.CREATE_CUSTOMER,
            {"organizationNumber": "978911226", "isSupplier": True, "isCustomer": False},
            {},
        ),
        (
            "Me har ein ny tilsett som heiter Gunnhild Eide, fodd 21. June 1997. Opprett vedkomande som tilsett med e-post gunnhild.eide@example.org og startdato 28. June 2026.",
            TaskType.CREATE_EMPLOYEE,
            {"birthDate": "1997-06-21", "startDate": "2026-06-28"},
            {},
        ),
        (
            'Opprett produktet "Konsulenttimar" med produktnummer 3923. Prisen er 26400 kr eksklusiv MVA, og standard MVA-sats pa 25 % skal nyttast.',
            TaskType.CREATE_PRODUCT,
            {"productNumber": "3923", "vatPercentage": 25.0, "priceExcludingVatCurrency": 26400.0},
            {},
        ),
        (
            'Opprett tre avdelingar i Tripletex: "Okonomi", "Administrasjon" og "Innkjop".',
            TaskType.CREATE_DEPARTMENT,
            {"departmentNames": "Okonomi||Administrasjon||Innkjop"},
            {},
        ),
        (
            'Crea el proyecto "Implementacion Dorada" vinculado al cliente Dorada SL (org. no 831075392). El director del proyecto es Isabel Rodriguez (isabel.rodriguez@example.org).',
            TaskType.CREATE_PROJECT,
            {"name": "Implementacion Dorada"},
            {"customer.organizationNumber": "831075392", "project_manager.email": "isabel.rodriguez@example.org"},
        ),
        (
            'Crie o projeto "Integracao Porto" vinculado ao cliente Porto Alegre Lda (org. no 872798277). O gerente de projeto e Andre Oliveira (andre.oliveira@example.org).',
            TaskType.CREATE_PROJECT,
            {"name": "Integracao Porto"},
            {"customer.organizationNumber": "872798277", "project_manager.email": "andre.oliveira@example.org"},
        ),
        (
            'Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).',
            TaskType.CREATE_PROJECT,
            {"name": "Implementacao Rio"},
            {"customer.organizationNumber": "827937223", "project_manager.email": "goncalo.oliveira@example.org"},
        ),
        (
            'Erstellen Sie das Produkt "Datenberatung" mit der Produktnummer 7855. Der Preis betragt 41550 NOK ohne MwSt., mit dem Standardsatz von 25 %.',
            TaskType.CREATE_PRODUCT,
            {"productNumber": "7855", "vatPercentage": 25.0, "priceExcludingVatCurrency": 41550.0},
            {},
        ),
            (
                'Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) pa 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.',
                TaskType.CREATE_INVOICE,
                {"invoiceDate": TODAY_ISO},
                {"customer.organizationNumber": "845762686", "order.description": "Skylagring", "invoice.description": "Skylagring"},
            ),
        (
            'O cliente Floresta Lda (org. no 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.',
            TaskType.CREATE_INVOICE,
            {"markAsPaid": True},
            {"customer.organizationNumber": "916058896", "invoice.description": "Desenvolvimento de sistemas"},
        ),
    ],
)
def test_hidden_prompt_corpus_parse_and_validate(
    prompt: str,
    task_type: TaskType,
    field_expectations: dict,
    related_expectations: dict,
) -> None:
    validated = validate_and_normalize_task(parse_prompt(prompt)).parsed_task

    assert validated.task_type == task_type
    for key, value in field_expectations.items():
        assert validated.fields[key] == value
    for dotted_key, value in related_expectations.items():
        top_key, nested_key = dotted_key.split(".", 1)
        assert validated.related_entities[top_key][nested_key] == value


@pytest.mark.parametrize(
    ("prompt", "payload_key", "required_pairs", "forbidden_keys"),
    [
        (
            'Opprett produktet "Konsulenttimar" med produktnummer 3923. Prisen er 26400 kr eksklusiv MVA, og standard MVA-sats pa 25 % skal nyttast.',
            "product_payload",
            {"name": "Konsulenttimar", "priceExcludingVatCurrency": 26400},
            {"productNumber", "vatPercentage"},
        ),
        (
            "Me har ein ny tilsett som heiter Gunnhild Eide, fodd 21. June 1997. Opprett vedkomande som tilsett med e-post gunnhild.eide@example.org og startdato 28. June 2026.",
            "employee_payload",
            {"email": "gunnhild.eide@example.org", "dateOfBirth": "1997-06-21"},
            {"dateFrom"},
        ),
        (
            'Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) pa 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.',
            "invoice_payload",
            {"invoiceDate": TODAY_ISO},
            {"sendByEmail"},
        ),
        (
            'O cliente Floresta Lda (org. no 916058896) tem uma fatura pendente de 30450 NOK sem IVA por "Desenvolvimento de sistemas". Registe o pagamento total desta fatura.',
            "invoice_payment_payload",
            {"paymentDate": TODAY_ISO, "amountPaidCurrency": "30450.0"},
            {"sendByEmail"},
        ),
        (
            "Registe o fornecedor Solmar Lda com numero de organizacao 978911226. E-mail: faktura@solmarlda.no.",
            "customer_payload",
            {"organizationNumber": "978911226", "isSupplier": True, "isCustomer": False},
            {"address", "postalCode", "city"},
        ),
    ],
)
def test_hidden_prompt_corpus_payload_contracts(
    prompt: str,
    payload_key: str,
    required_pairs: dict,
    forbidden_keys: Set[str],
) -> None:
    recorded: dict = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
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
    payload = recorded[payload_key]
    for key, value in required_pairs.items():
        assert payload[key] == value
    for key in forbidden_keys:
        assert key not in payload
    app.dependency_overrides.clear()
